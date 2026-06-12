import json
import time
import traceback
from typing import Optional

from memory.procedural_memory import procedural_memory
from core.cognitive_runtime import ToolCallRecord, TurnContext


ERROR_PATTERNS = {
    "timeout": ["timeout", "timed out", "did not respond in time"],
    "auth": ["auth", "api key", "unauthorized", "401", "403"],
    "rate_limit": ["rate limit", "429", "too many requests"],
    "not_found": ["not found", "no such", "does not exist", "404"],
    "permission": ["permission", "access denied", "denied"],
    "parse": ["parse", "json decode", "unexpected format"],
    "empty": ["none", "empty", "no result", "no data", "no response"],
}


def classify_error(error_str: str) -> str:
    error_lower = error_str.lower()
    for category, patterns in ERROR_PATTERNS.items():
        for pattern in patterns:
            if pattern in error_lower:
                return category
    return "unknown"


def evaluate_tool_outcome(record: ToolCallRecord) -> tuple[str, str]:
    if record.success:
        result_lower = record.result.lower()
        if not record.result or record.result.strip() in ("Done.", "Ok.", ""):
            return "empty_result", "Tool completed but returned empty. Verify parameters or try a different tool."
        if "error" in result_lower or "fail" in result_lower or "sorry" in result_lower:
            return "partial_failure", "Tool reported an issue. Review the output carefully."
        if "unknown" in result_lower or "don't know" in result_lower:
            return "inconclusive", "Tool could not find the info. Try different search terms or a different tool."
        return "success", "Tool executed successfully."
    else:
        error_type = classify_error(record.result)
        return error_type, f"Tool failed with {error_type} error."


def _llm_analyze(record: ToolCallRecord) -> Optional[tuple[str, str, str]]:
    try:
        from core.llm_client import llm
    except ImportError:
        return None

    if not llm.has_any_key:
        return None

    prompt = (
        f"Analyze this tool call and provide:\n"
        f"1. outcome: one word (success|empty_result|partial_failure|timeout|auth|rate_limit|not_found|parse|unknown)\n"
        f"2. lesson: 1 sentence, specific, actionable\n"
        f"3. suggestion: what to do differently next time\n\n"
        f"Tool: {record.name}\n"
        f"Arguments: {json.dumps(record.arguments)[:300]}\n"
        f"Result: {record.result[:400]}\n"
        f"Success: {record.success}\n\n"
        f"Format: JSON with keys: outcome, lesson, suggestion"
    )

    try:
        raw = llm.chat(
            prompt,
            system="Analyze tool calls and return JSON with outcome, lesson, suggestion.",
            max_tokens=256,
            temperature=0.1,
        )
        clean = raw.strip()
        if clean.startswith("```"):
            parts = clean.split("```")
            clean = parts[1] if len(parts) > 1 else clean
            clean = clean[4:] if clean.startswith("json") else clean
        data = json.loads(clean.strip().rstrip("`").strip())
        outcome = data.get("outcome", "unknown")
        lesson = data.get("lesson", "")
        suggestion = data.get("suggestion", "")
        return outcome, lesson, suggestion
    except Exception:
        return None


class ReflexionEngine:
    def __init__(self):
        self._last_reflexion_time = 0.0
        self._reflexion_interval = 60.0

    _SILENT_TOOLS = {"shutdown_nox", "save_memory"}

    def evaluate_tool_call(self, record: ToolCallRecord):
        if record.name in self._SILENT_TOOLS:
            return

        llm_result = _llm_analyze(record)
        if llm_result:
            outcome, lesson, suggestion = llm_result
            lesson = f"{lesson} {suggestion}" if suggestion else lesson
        else:
            outcome, lesson = evaluate_tool_outcome(record)

        if outcome != "success":
            print(f"[Reflexion] {record.name}: {outcome} — {lesson[:100]}")

        procedural_memory.save_reflexion(
            lesson=lesson,
            pattern=record.name,
            category=outcome,
            outcome=outcome,
        )

    def should_reflect(self) -> bool:
        now = time.time()
        if now - self._last_reflexion_time > self._reflexion_interval:
            self._last_reflexion_time = now
            return True
        return False

    def get_reflexion_context(self) -> str:
        reflexions = procedural_memory.get_unapplied_reflexions(limit=5)
        if not reflexions:
            return ""
        lines = []
        for r in reflexions:
            if r["outcome"] != "success":
                lines.append(f"  - [{r['category']}] {r['lesson']}")
        if not lines:
            return ""
        return "[REFLEXION — lessons from past tool usage]\n" + "\n".join(lines) + "\n"

    def get_tool_warning(self, tool_name: str) -> Optional[str]:
        reliability = procedural_memory.get_tool_reliability(tool_name)
        if reliability is not None and reliability < 0.5:
            failures_pct = int((1 - reliability) * 100)
            return (
                f"[CAUTION] Tool '{tool_name}' has {failures_pct}% failure rate historically. "
                f"Double-check parameters before calling."
            )
        return None

    def get_tool_usage_tips(self) -> str:
        stats = procedural_memory.get_tool_stats()
        if stats["total_calls"] < 5:
            return ""
        lines = []
        high_failures = [t for t in stats["by_tool"] if t["count"] > 0 and t["ok"] / t["count"] < 0.5]
        if high_failures:
            lines.append("[TOOL USAGE PATTERNS]")
            for t in high_failures:
                failures = t["count"] - t["ok"]
                lines.append(f"  - {t['tool_name']}: {failures}/{t['count']} failures. Use with caution.")
        return "\n".join(lines)

    def mark_pattern_applied(self, tool_name: str):
        if tool_name:
            procedural_memory.mark_reflexion_applied(tool_name)


reflexion_engine = ReflexionEngine()
