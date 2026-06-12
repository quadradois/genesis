import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from memory.procedural_memory import procedural_memory

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_PATH = BASE_DIR / "memory" / "user_profile.json"


class UserProfile:
    def __init__(self):
        self._data: dict = self._load()

    def _load(self) -> dict:
        try:
            if PROFILE_PATH.exists():
                return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {
            "common_requests": {},
            "preferred_tools": {},
            "interaction_patterns": [],
            "language_preferences": {"primary": "", "languages": []},
            "expertise_areas": [],
            "last_updated": "",
        }

    def _save(self):
        self._data["last_updated"] = datetime.now().isoformat()
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_PATH.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def record_tool_usage(self, tool_name: str, success: bool):
        tools = self._data["preferred_tools"]
        if tool_name not in tools:
            tools[tool_name] = {"calls": 0, "successes": 0}
        tools[tool_name]["calls"] += 1
        if success:
            tools[tool_name]["successes"] += 1
        self._save()

    def record_request_pattern(self, category: str, tool_used: str):
        requests = self._data["common_requests"]
        key = f"{category}:{tool_used}"
        if key not in requests:
            requests[key] = {"category": category, "tool": tool_used, "count": 0}
        requests[key]["count"] += 1
        self._save()

    def get_tool_reliability(self, tool_name: str) -> float:
        tools = self._data["preferred_tools"]
        info = tools.get(tool_name, {"calls": 0, "successes": 0})
        if info["calls"] == 0:
            return 0.0
        return info["successes"] / info["calls"]

    def get_failing_tools(self, threshold: float = 0.5) -> list[tuple[str, float]]:
        result = []
        for name, info in self._data["preferred_tools"].items():
            if info["calls"] >= 2:
                rate = info["successes"] / info["calls"]
                if rate < threshold:
                    result.append((name, rate))
        return sorted(result, key=lambda x: x[1])

    def get_top_tools(self, limit: int = 3) -> list[str]:
        tools = self._data["preferred_tools"]
        sorted_tools = sorted(
            tools.items(),
            key=lambda x: (x[1]["successes"] / max(x[1]["calls"], 1), x[1]["calls"]),
            reverse=True,
        )
        return [t[0] for t in sorted_tools[:limit]]

    def get_profile_summary(self) -> str:
        parts = []
        top_tools = self.get_top_tools(3)
        if top_tools:
            parts.append(f"Most reliable tools: {', '.join(top_tools)}")

        patterns = self._data["common_requests"]
        if patterns:
            top_patterns = sorted(patterns.items(), key=lambda x: x[1]["count"], reverse=True)[:3]
            pattern_strs = [f"{p[1]['category']} (via {p[1]['tool']})" for p in top_patterns]
            parts.append(f"Frequent request types: {', '.join(pattern_strs)}")

        failing = self.get_failing_tools(threshold=0.5)
        if failing:
            names = [f for f, _ in failing[:2]]
            parts.append(f"Tools needing caution: {', '.join(names)}")

        return "\n".join(parts)


class ProceduralOptimizer:
    def __init__(self):
        self._last_optimization = time.time()
        self._optimization_interval = 300.0
        self._consecutive_same_tool_errors = 0

    def should_optimize(self) -> bool:
        return time.time() - self._last_optimization > self._optimization_interval

    def mark_optimized(self):
        self._last_optimization = time.time()

    def check_tool_loop(self, tool_name: str, success: bool) -> Optional[str]:
        if not success and self._consecutive_same_tool_errors > 2:
            self._consecutive_same_tool_errors = 0
            return f"[OPTIMIZATION] Tool '{tool_name}' keeps failing. Switch approach."
        if success:
            self._consecutive_same_tool_errors = 0
        else:
            self._consecutive_same_tool_errors += 1
        return None

    def generate_context_prompt(self) -> str:
        if not self.should_optimize():
            return ""
        self.mark_optimized()

        stats = procedural_memory.get_tool_stats()
        if stats["total_calls"] < 3:
            return ""

        lines = ["[SELF-IMPROVEMENT — procedural optimization]"]
        total = stats["total_calls"]
        failures = stats["failures"]
        if failures > 0:
            pct = (failures / total) * 100
            lines.append(f"  - Tool failure rate: {pct:.0f}% ({failures}/{total})")

        high_fail_tools = [
            t for t in stats["by_tool"]
            if t["count"] >= 2 and t["ok"] / t["count"] < 0.5
        ]
        for t in high_fail_tools:
            lines.append(
                f"  - {t['tool_name']}: {t['count'] - t['ok']}/{t['count']} failures. "
                f"Verify parameters before calling."
            )

        return "\n".join(lines) + "\n"


user_profile = UserProfile()
procedural_optimizer = ProceduralOptimizer()
