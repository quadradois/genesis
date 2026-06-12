import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class ThinkingStage(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    REASONING = "reasoning"
    CALLING_TOOL = "calling_tool"
    EVALUATING = "evaluating"
    RESPONDING = "responding"
    ERROR = "error"


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict
    started_at: float
    duration_ms: float = 0
    result: str = ""
    success: bool = True
    error_type: str = ""


@dataclass
class TurnContext:
    turn_index: int = 0
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    user_input: str = ""
    started_at: float = 0.0
    thinking_stage: ThinkingStage = ThinkingStage.IDLE
    cancelled: bool = False


class IterationBudget:
    def __init__(self, max_tool_calls_per_turn: int = 8, max_consecutive_errors: int = 3):
        self.max_tool_calls = max_tool_calls_per_turn
        self.max_errors = max_consecutive_errors
        self._consecutive_errors = 0

    def can_call_tool(self, turn: TurnContext) -> bool:
        if len(turn.tool_calls) >= self.max_tool_calls:
            return False
        if self._consecutive_errors >= self.max_errors:
            return False
        return True

    def record_result(self, success: bool):
        if success:
            self._consecutive_errors = 0
        else:
            self._consecutive_errors += 1

    @property
    def consecutive_errors(self) -> int:
        return self._consecutive_errors

    def reset(self):
        self._consecutive_errors = 0


class ThinkingPipeline:
    def __init__(self):
        self._hooks: list[Callable[[ThinkingStage], None]] = []

    def add_hook(self, hook: Callable[[ThinkingStage], None]):
        self._hooks.append(hook)

    def set_stage(self, turn: TurnContext, stage: ThinkingStage):
        turn.thinking_stage = stage
        for hook in self._hooks:
            try:
                hook(stage)
            except Exception:
                pass


class CognitiveRuntime:
    def __init__(self, max_tool_calls: int = 8):
        self.budget = IterationBudget(max_tool_calls_per_turn=max_tool_calls)
        self.pipeline = ThinkingPipeline()
        self.current_turn: Optional[TurnContext] = None
        self._total_turns = 0
        self._total_tool_calls = 0

    def start_turn(self, user_input: str = "") -> TurnContext:
        turn = TurnContext(
            turn_index=self._total_turns,
            user_input=user_input,
            started_at=time.time(),
        )
        self.current_turn = turn
        self.pipeline.set_stage(turn, ThinkingStage.PROCESSING)
        return turn

    def end_turn(self):
        if self.current_turn:
            self._total_turns += 1
            self._total_tool_calls += len(self.current_turn.tool_calls)
            self.pipeline.set_stage(self.current_turn, ThinkingStage.IDLE)
        self.current_turn = None

    def start_tool_call(self, name: str, arguments: dict) -> ToolCallRecord:
        record = ToolCallRecord(
            name=name,
            arguments=arguments,
            started_at=time.time(),
        )
        if self.current_turn:
            self.current_turn.tool_calls.append(record)
        self.pipeline.set_stage(self.current_turn or TurnContext(), ThinkingStage.CALLING_TOOL)
        return record

    def finish_tool_call(self, record: ToolCallRecord, result: str, success: bool, error_type: str = ""):
        record.duration_ms = (time.time() - record.started_at) * 1000
        record.result = result
        record.success = success
        record.error_type = error_type
        self.budget.record_result(success)
        if self.current_turn:
            self.pipeline.set_stage(self.current_turn, ThinkingStage.EVALUATING)

    def can_proceed(self) -> bool:
        if not self.current_turn:
            return True
        if not self.budget.can_call_tool(self.current_turn):
            self.current_turn.cancelled = True
            return False
        return True

    @property
    def total_turns(self) -> int:
        return self._total_turns

    @property
    def total_tool_calls(self) -> int:
        return self._total_tool_calls
