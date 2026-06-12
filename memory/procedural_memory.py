import asyncio
import json
import math
import re
import sqlite3
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

_local = threading.local()
_lock = threading.Lock()
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "memory" / "procedural.db"
_cleanup_done = False


def _close_conns():
    for t in list(_local.__dict__.keys()):
        try:
            conn = getattr(_local, t, None)
            if conn:
                conn.close()
                delattr(_local, t)
        except Exception:
            pass


def _get_conn() -> sqlite3.Connection:
    global _cleanup_done
    if not _cleanup_done:
        import atexit
        atexit.register(_close_conns)
        _cleanup_done = True
    conn = getattr(_local, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _init_db(conn)
        _local.conn = conn
    return conn


def _init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at  TEXT NOT NULL,
            ended_at    TEXT,
            turn_count  INTEGER DEFAULT 0,
            summary     TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS memories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER,
            category    TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            importance  INTEGER DEFAULT 1,
            access_count INTEGER DEFAULT 0,
            last_accessed TEXT,
            consolidated INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS reflexions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER,
            lesson      TEXT NOT NULL,
            pattern     TEXT DEFAULT '',
            category    TEXT DEFAULT 'general',
            outcome     TEXT DEFAULT 'neutral',
            created_at  TEXT NOT NULL,
            applied     INTEGER DEFAULT 0,
            applied_at  TEXT,
            apply_count INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS tool_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER,
            turn_index  INTEGER DEFAULT 0,
            tool_name   TEXT NOT NULL,
            arguments   TEXT DEFAULT '{}',
            result      TEXT DEFAULT '',
            duration_ms REAL DEFAULT 0,
            success     INTEGER DEFAULT 1,
            error_type  TEXT DEFAULT '',
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
    """)

    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(content=memories, content_rowid=id, category, key, value)")
    except sqlite3.OperationalError:
        pass

    for trigger in ["memories_ai", "memories_ad", "memories_au"]:
        try:
            conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        except sqlite3.OperationalError:
            pass

    try:
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, category, key, value)
                VALUES (new.id, new.category, new.key, new.value);
            END
        """)
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, category, key, value)
                VALUES ('delete', old.id, old.category, old.key, old.value);
            END
        """)
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, category, key, value)
                VALUES ('delete', old.id, old.category, old.key, old.value);
                INSERT INTO memories_fts(rowid, category, key, value)
                VALUES (new.id, new.category, new.key, new.value);
            END
        """)
    except sqlite3.OperationalError:
        pass


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z\d]+", text.lower()))


def _compute_relevance(memory: dict, now: datetime) -> float:
    try:
        created = datetime.fromisoformat(memory["created_at"])
    except (ValueError, TypeError):
        created = now
    days_since = max(0, (now - created).days)
    recency_weight = 1.0 / (1.0 + days_since * 0.1)
    access_score = 1.0 + math.log2(memory.get("access_count", 0) + 1)
    importance = memory.get("importance", 1)
    return importance * access_score * recency_weight


class ProceduralMemory:
    def __init__(self):
        self._session_id: Optional[int] = None
        self._turn_index = 0

    # --- Sync methods (for sync callers / tests) ---

    def start_session(self) -> int:
        with _lock:
            conn = _get_conn()
            now = datetime.now().isoformat()
            cur = conn.execute(
                "INSERT INTO sessions (started_at) VALUES (?)", (now,)
            )
            conn.commit()
            self._session_id = cur.lastrowid
            return self._session_id

    def end_session(self, summary: str = ""):
        if not self._session_id:
            return
        with _lock:
            conn = _get_conn()
            conn.execute(
                "UPDATE sessions SET ended_at=?, summary=? WHERE id=?",
                (datetime.now().isoformat(), summary, self._session_id),
            )
            conn.commit()

    def save_conversation(self, role: str, content: str):
        if not self._session_id:
            return
        with _lock:
            conn = _get_conn()
            conn.execute(
                "INSERT INTO conversations (session_id, role, content, timestamp) VALUES (?,?,?,?)",
                (self._session_id, role, content, datetime.now().isoformat()),
            )
            conn.commit()
            conn.execute(
                "UPDATE sessions SET turn_count = turn_count + 1 WHERE id = ?",
                (self._session_id,),
            )
            conn.commit()

    def save_memory(self, category: str, key: str, value: str, importance: int = 1):
        with _lock:
            conn = _get_conn()
            existing = conn.execute(
                "SELECT id, value, importance FROM memories WHERE category=? AND key=?",
                (category, key),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE memories SET value=?, importance=MAX(importance,?), created_at=?, consolidated=0 WHERE id=?",
                    (value, importance, datetime.now().isoformat(), existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO memories (session_id, category, key, value, created_at, importance) VALUES (?,?,?,?,?,?)",
                    (self._session_id, category, key, value, datetime.now().isoformat(), importance),
                )
            conn.commit()

    def search_memories(self, query: str, limit: int = 10) -> list[dict]:
        try:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT m.* FROM memories_fts f JOIN memories m ON f.rowid = m.id "
                "WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
            results = [dict(r) for r in rows]
            with _lock:
                for r in results:
                    conn.execute(
                        "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                        (datetime.now().isoformat(), r["id"]),
                    )
                conn.commit()
            return results
        except sqlite3.OperationalError:
            return []

    def search_memories_relevant(self, query: str, limit: int = 10) -> list[dict]:
        try:
            conn = _get_conn()
            tokens = _tokenize(query)
            if not tokens:
                return []
            fts_query = " OR ".join(f'"{t}"' for t in tokens)
            fts_query += " OR " + " OR ".join(f"{t}*" for t in tokens)
            rows = conn.execute(
                "SELECT m.* FROM memories_fts f JOIN memories m ON f.rowid = m.id "
                "WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, limit * 3),
            ).fetchall()
            results = [dict(r) for r in rows]
            now = datetime.now()
            scored = []
            for r in results:
                value_tokens = _tokenize(r["value"])
                key_tokens = _tokenize(r["key"])
                overlap = len(tokens & value_tokens) + len(tokens & key_tokens) * 2
                textual_score = 1.0 + overlap
                relevance = _compute_relevance(r, now)
                combined = relevance * textual_score
                scored.append((combined, r))
            scored.sort(key=lambda x: -x[0])
            with _lock:
                for r in results:
                    conn.execute(
                        "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                        (datetime.now().isoformat(), r["id"]),
                    )
                conn.commit()
            return [r for _, r in scored[:limit]]
        except sqlite3.OperationalError:
            return []

    def get_all_memories(self, category: Optional[str] = None) -> list[dict]:
        conn = _get_conn()
        if category:
            rows = conn.execute(
                "SELECT * FROM memories WHERE category=? ORDER BY importance DESC, created_at DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories ORDER BY importance DESC, created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_top_memories(self, max_chars: int = 1500) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM memories").fetchall()
        if not rows:
            return []
        now = datetime.now()
        scored = [(_compute_relevance(dict(r), now), dict(r)) for r in rows]
        scored.sort(key=lambda x: -x[0])
        result = []
        char_count = 0
        for score, m in scored:
            entry_len = len(f"  {m['category']}: {m['key']} = {m['value']}") + 1
            if char_count + entry_len > max_chars and result:
                break
            result.append(m)
            char_count += entry_len
        return result

    def log_tool_call(self, tool_name: str, arguments: dict, result: str, duration_ms: float, success: bool, error_type: str = ""):
        if not self._session_id:
            return
        with _lock:
            conn = _get_conn()
            conn.execute(
                "INSERT INTO tool_log (session_id, turn_index, tool_name, arguments, result, duration_ms, success, error_type, timestamp) VALUES (?,?,?,?,?,?,?,?,?)",
                (self._session_id, self._turn_index, tool_name, json.dumps(arguments), str(result)[:500], duration_ms, 1 if success else 0, error_type, datetime.now().isoformat()),
            )
            conn.commit()

    def save_reflexion(self, lesson: str, pattern: str = "", category: str = "general", outcome: str = "neutral"):
        if not self._session_id:
            return
        with _lock:
            conn = _get_conn()
            existing = conn.execute(
                "SELECT id, apply_count FROM reflexions WHERE pattern=? AND category=? AND outcome=? AND applied=0 ORDER BY created_at DESC LIMIT 1",
                (pattern, category, outcome),
            ).fetchone()
            if existing and outcome != "success":
                conn.execute(
                    "UPDATE reflexions SET lesson=?, created_at=? WHERE id=?",
                    (lesson, datetime.now().isoformat(), existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO reflexions (session_id, lesson, pattern, category, outcome, created_at) VALUES (?,?,?,?,?,?)",
                    (self._session_id, lesson, pattern, category, outcome, datetime.now().isoformat()),
                )
            conn.commit()

    def mark_reflexion_applied(self, pattern: str) -> None:
        with _lock:
            conn = _get_conn()
            conn.execute(
                "UPDATE reflexions SET applied=1, applied_at=?, apply_count=apply_count+1 WHERE pattern=? AND applied=0",
                (datetime.now().isoformat(), pattern),
            )
            conn.commit()

    def get_unapplied_reflexions(self, limit: int = 5) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM reflexions WHERE applied=0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_reflexions(self, limit: int = 5) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM reflexions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_reflexions_by_category(self, category: str, limit: int = 5) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM reflexions WHERE category=? ORDER BY created_at DESC LIMIT ?",
            (category, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session_history(self, session_id: Optional[int] = None, limit: int = 20) -> list[dict]:
        sid = session_id or self._session_id
        if not sid:
            return []
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM conversations WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
            (sid, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_tool_stats(self) -> dict:
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) as c FROM tool_log").fetchone()["c"]
        successes = conn.execute("SELECT COUNT(*) as c FROM tool_log WHERE success=1").fetchone()["c"]
        failures = total - successes
        by_tool = conn.execute(
            "SELECT tool_name, COUNT(*) as count, SUM(success) as ok FROM tool_log GROUP BY tool_name ORDER BY count DESC"
        ).fetchall()
        return {
            "total_calls": total,
            "successes": successes,
            "failures": failures,
            "by_tool": [dict(r) for r in by_tool],
        }

    def get_tool_reliability(self, tool_name: str) -> Optional[float]:
        conn = _get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as count, SUM(success) as ok FROM tool_log WHERE tool_name=?",
            (tool_name,),
        ).fetchone()
        if not row or row["count"] == 0:
            return None
        return row["ok"] / row["count"]

    def get_recent_sessions(self, limit: int = 5) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation_context(self, limit: int = 10) -> str:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
            (self._session_id, limit),
        ).fetchall()
        lines = []
        for r in reversed(rows):
            prefix = "User: " if r["role"] == "user" else "Nox: "
            content = r["content"][:200]
            lines.append(f"{prefix}{content}")
        return "\n".join(lines)

    def format_memories_for_prompt(self, max_chars: int = 1500) -> str:
        memories = self.get_top_memories(max_chars=max_chars)
        if not memories:
            return ""
        lines = []
        for m in memories:
            lines.append(f"  {m['category']}: {m['key']} = {m['value']}")
        text = "Procedural memories:\n" + "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars-3] + "..."
        return text

    def format_reflexions_for_prompt(self, max_items: int = 3) -> str:
        reflexions = self.get_unapplied_reflexions(limit=max_items)
        if not reflexions:
            return ""
        lines = ["Lessons learned from past sessions:"]
        for r in reflexions:
            lines.append(f"  - {r['lesson']}")
        return "\n".join(lines)

    def consolidate_memories(self) -> int:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM memories WHERE consolidated=0 ORDER BY importance DESC, created_at DESC"
        ).fetchall()
        if not rows:
            return 0

        groups: dict[str, list[dict]] = {}
        for r in rows:
            m = dict(r)
            key = f"{m['category']}:::{m['key'].lower().strip()}"
            groups.setdefault(key, []).append(m)

        merged = 0
        for key, group in groups.items():
            if len(group) < 2:
                conn.execute("UPDATE memories SET consolidated=1 WHERE id=?", (group[0]["id"],))
                continue
            best = group[0]
            for m in group[1:]:
                merged += 1
                conn.execute(
                    "UPDATE memories SET value=?, importance=MAX(importance,?), "
                    "access_count=access_count+?, last_accessed=?, consolidated=1 WHERE id=?",
                    (best["value"], best["importance"], m["access_count"], datetime.now().isoformat(), m["id"]),
                )
            conn.execute(
                "UPDATE memories SET consolidated=1 WHERE id=?",
                (best["id"],),
            )
        conn.commit()

        try:
            conn.execute("DELETE FROM memories WHERE consolidated=1 AND id NOT IN (SELECT MAX(id) FROM memories WHERE consolidated=1 GROUP BY category, key)")
            merged2 = conn.execute("SELECT changes() as c").fetchone()["c"]
            conn.commit()
            merged += merged2
        except sqlite3.OperationalError:
            pass

        return merged

    def prune_old_reflexions(self, max_days: int = 30):
        conn = _get_conn()
        cutoff = (datetime.now() - __import__("datetime").timedelta(days=max_days)).isoformat()
        conn.execute("DELETE FROM reflexions WHERE created_at < ? AND applied=1 AND apply_count=0", (cutoff,))
        conn.commit()

    def increment_turn(self):
        self._turn_index += 1

    # --- Async wrappers (for asyncio callers) ---

    async def async_start_session(self) -> int:
        return await asyncio.to_thread(self.start_session)

    async def async_end_session(self, summary: str = ""):
        return await asyncio.to_thread(self.end_session, summary)

    async def async_save_conversation(self, role: str, content: str):
        return await asyncio.to_thread(self.save_conversation, role, content)

    async def async_save_memory(self, category: str, key: str, value: str, importance: int = 1):
        return await asyncio.to_thread(self.save_memory, category, key, value, importance)

    async def async_search_memories_relevant(self, query: str, limit: int = 10) -> list[dict]:
        return await asyncio.to_thread(self.search_memories_relevant, query, limit)

    async def async_log_tool_call(self, tool_name: str, arguments: dict, result: str, duration_ms: float, success: bool, error_type: str = ""):
        return await asyncio.to_thread(self.log_tool_call, tool_name, arguments, result, duration_ms, success, error_type)

    async def async_save_reflexion(self, lesson: str, pattern: str = "", category: str = "general", outcome: str = "neutral"):
        return await asyncio.to_thread(self.save_reflexion, lesson, pattern, category, outcome)

    async def async_consolidate_memories(self) -> int:
        return await asyncio.to_thread(self.consolidate_memories)

    async def async_prune_old_reflexions(self, max_days: int = 30):
        return await asyncio.to_thread(self.prune_old_reflexions, max_days)

    async def async_get_tool_reliability(self, tool_name: str) -> Optional[float]:
        return await asyncio.to_thread(self.get_tool_reliability, tool_name)

    async def async_mark_reflexion_applied(self, pattern: str):
        return await asyncio.to_thread(self.mark_reflexion_applied, pattern)

    @property
    def session_id(self) -> Optional[int]:
        return self._session_id


procedural_memory = ProceduralMemory()
