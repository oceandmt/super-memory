"""Cross-session synthesis, shared recall, and cross-agent conflict tools."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .config import load_config


def _rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


class SynthesisTools:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.db_path = Path(self.config.workspace_root) / self.config.sqlite_path
        self.ensure_tables()

    def ensure_tables(self) -> None:
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cross_agent_conflicts (
                    id TEXT PRIMARY KEY,
                    topic TEXT,
                    agent_a TEXT,
                    agent_b TEXT,
                    memory_a_id TEXT,
                    memory_b_id TEXT,
                    content_a TEXT,
                    content_b TEXT,
                    status TEXT DEFAULT 'open',
                    resolution TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TEXT
                )
            """)

    def cross_session_synthesis(self, peer_id: str = "boss", window_days: int = 30, depth: int = 2) -> dict[str, Any]:
        """Synthesize recent Honcho events for a peer into conclusions."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            events = _rows(conn, """
                SELECT session_id, observer_peer_id, observed_peer_id, content, created_at
                FROM honcho_events
                WHERE (observed_peer_id = ? OR observer_peer_id = ?)
                  AND created_at >= datetime('now', ?)
                ORDER BY created_at DESC
                LIMIT 200
            """, (peer_id, peer_id, f"-{int(window_days)} days"))
            text = "\n".join(e["content"] for e in events)
            insights = self._derive_insights(text, depth=depth)
            saved = []
            for insight in insights:
                cid = conn.execute("SELECT lower(hex(randomblob(16)))").fetchone()[0]
                conn.execute("""
                    INSERT INTO honcho_conclusions
                    (id, about_peer_id, content, confidence, source, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, 'cross_session_synthesis', ?, CURRENT_TIMESTAMP)
                """, (cid, peer_id, insight, 0.75, json.dumps({"evidence_count": len(events), "status": "active"})))
                saved.append({"id": cid, "content": insight})
        return {"ok": True, "peer_id": peer_id, "window_days": window_days, "events": len(events), "insights": saved}

    def _derive_insights(self, text: str, depth: int = 2) -> list[str]:
        lines: list[str] = []
        low = text.lower()
        patterns = [
            ("prefer", "Boss preferences are repeatedly mentioned and should be prioritized."),
            ("trading", "Trading workflows recur across sessions; preserve blackout/news risk context."),
            ("facebook", "Social posting workflows recur; default public Business Suite behavior matters."),
            ("memory", "Memory-system work recurs; canonical markdown-first routing remains important."),
            ("deploy", "Deployment tasks recur; verify VPS service/config/plugin health after changes."),
            ("heartbeat", "Long-running implementation should use heartbeat progress tracking."),
        ]
        for key, insight in patterns:
            if key in low:
                lines.append(insight)
        if depth >= 3 and "block" in low:
            lines.append("Repeated blockers should be promoted into durable blocker/register memory.")
        return lines[:8] or ["Cross-session synthesis completed; no strong recurring pattern detected."]

    def shared_recall(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Recall shared-scope memories."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            rows = _rows(conn, """
                SELECT id, content, type, scope, agent_id, session_id, project, tags_json, created_at
                FROM memories
                WHERE scope = 'shared' AND content LIKE ?
                ORDER BY created_at DESC LIMIT ?
            """, (f"%{query}%", max(1, min(limit, 100))))
        for row in rows:
            try:
                row["tags"] = json.loads(row.pop("tags_json") or "[]")
            except json.JSONDecodeError:
                row["tags"] = []
        return {"ok": True, "query": query, "memories": rows, "count": len(rows)}

    def promote_to_shared(self, memory_id: str) -> dict[str, Any]:
        """Promote a memory to shared scope."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            cur = conn.execute("UPDATE memories SET scope = 'shared' WHERE id = ?", (memory_id,))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
        return {"ok": cur.rowcount > 0, "memory_id": memory_id, "scope": "shared"}

    def cross_agent_conflicts(self, action: str = "list", topic: str | None = None, limit: int = 20, conflict_id: str | None = None, resolution: str | None = None) -> dict[str, Any]:
        """List/check/resolve simple cross-agent conflict candidates."""
        if action == "resolve" and conflict_id:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                cur = conn.execute("""
                    UPDATE cross_agent_conflicts
                    SET status='resolved', resolution=?, resolved_at=CURRENT_TIMESTAMP
                    WHERE id=?
                """, (resolution or "resolved", conflict_id))
            return {"ok": cur.rowcount > 0, "conflict_id": conflict_id}
        if action == "check":
            return self._check_conflicts(topic or "", limit=limit)
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            rows = _rows(conn, "SELECT * FROM cross_agent_conflicts ORDER BY created_at DESC LIMIT ?", (limit,))
        return {"ok": True, "conflicts": rows, "count": len(rows)}

    def _check_conflicts(self, topic: str, limit: int = 20) -> dict[str, Any]:
        words = [w for w in re.findall(r"\w+", topic.lower()) if len(w) > 3]
        query = f"%{words[0] if words else topic}%"
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            rows = _rows(conn, """
                SELECT id, agent_id, content FROM memories
                WHERE content LIKE ? AND agent_id IS NOT NULL
                ORDER BY created_at DESC LIMIT ?
            """, (query, max(2, min(limit, 100))))
            conflicts = []
            for i, a in enumerate(rows):
                for b in rows[i+1:]:
                    if a["agent_id"] == b["agent_id"]:
                        continue
                    if self._opposes(a["content"], b["content"]):
                        cid = conn.execute("SELECT lower(hex(randomblob(16)))").fetchone()[0]
                        conn.execute("""
                            INSERT OR IGNORE INTO cross_agent_conflicts
                            (id, topic, agent_a, agent_b, memory_a_id, memory_b_id, content_a, content_b)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (cid, topic, a["agent_id"], b["agent_id"], a["id"], b["id"], a["content"], b["content"]))
                        conflicts.append(cid)
        return {"ok": True, "topic": topic, "created": len(conflicts), "conflict_ids": conflicts}

    def _opposes(self, a: str, b: str) -> bool:
        neg = ["not", "never", "disable", "reject", "blocked", "failed", "wrong"]
        pos = ["enable", "accept", "success", "passed", "correct", "allow"]
        la, lb = a.lower(), b.lower()
        return any(x in la for x in neg) and any(x in lb for x in pos) or any(x in lb for x in neg) and any(x in la for x in pos)


SYNTHESIS_TOOLS = [
    {"name": "super_memory_cross_session_synthesis", "description": "Synthesize Honcho events across sessions", "inputSchema": {"type": "object", "properties": {"peer_id": {"type": "string", "default": "boss"}, "window_days": {"type": "integer", "default": 30}, "depth": {"type": "integer", "default": 2}}, "required": []}},
    {"name": "super_memory_shared_recall", "description": "Recall shared-scope memories", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, "required": ["query"]}},
    {"name": "super_memory_promote_to_shared", "description": "Promote a memory to shared scope", "inputSchema": {"type": "object", "properties": {"memory_id": {"type": "string"}}, "required": ["memory_id"]}},
    {"name": "super_memory_cross_agent_conflicts", "description": "List/check/resolve cross-agent conflicts", "inputSchema": {"type": "object", "properties": {"action": {"type": "string", "default": "list"}, "topic": {"type": "string"}, "limit": {"type": "integer", "default": 20}, "conflict_id": {"type": "string"}, "resolution": {"type": "string"}}, "required": []}},
]
