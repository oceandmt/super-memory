"""Cross-agent memory query and comparison tools."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import load_config


def _rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    for k in ("tags_json", "metadata_json"):
        if k in row and isinstance(row[k], str):
            try:
                row[k[:-5] if k.endswith("_json") else k] = json.loads(row[k] or "null")
            except json.JSONDecodeError:
                row[k[:-5]] = row[k]
    return row


class CrossAgentTools:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.db_path = Path(self.config.workspace_root) / self.config.sqlite_path

    def cross_agent_recall(self, query: str, agent_id: str, limit: int = 10) -> dict[str, Any]:
        """Query memories filtered by agent_id."""
        like = f"%{query}%"
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            rows = _rows(conn, """
                SELECT id, layer, content, type, scope, agent_id, session_id, project,
                       tags_json, source, trust_score, created_at, metadata_json
                FROM memories
                WHERE agent_id = ? AND content LIKE ? AND layer = 'workspace_markdown'
                ORDER BY created_at DESC LIMIT ?
            """, (agent_id, like, limit))
        memories = [_decode(r) for r in rows]
        return {"ok": True, "agent_id": agent_id, "query": query, "memories": memories, "count": len(memories)}

    def cross_agent_honcho_ask(self, query: str, observer_agent: str, about_peer: str = "boss", limit: int = 10) -> dict[str, Any]:
        """Query Honcho events filtered by observer_peer_id."""
        like = f"%{query}%"
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            events = _rows(conn, """
                SELECT id, memory_id, workspace, session_id, observer_peer_id,
                       observed_peer_id, content, source, metadata_json, created_at
                FROM honcho_events
                WHERE observer_peer_id = ? AND (? = '' OR observed_peer_id = ?) AND content LIKE ?
                ORDER BY created_at DESC LIMIT ?
            """, (observer_agent, about_peer or "", about_peer or "", like, limit))
        return {"ok": True, "observer_agent": observer_agent, "about_peer": about_peer, "events": [_decode(e) for e in events], "count": len(events)}

    def cross_agent_summary(self, agent_id: str | None = None, days: int = 30) -> dict[str, Any]:
        """Summary of agent memories/activities."""
        where = "WHERE agent_id IS NOT NULL" + (" AND agent_id = ?" if agent_id else "")
        args: tuple[Any, ...] = (agent_id,) if agent_id else ()
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            layer_clause = " AND layer = 'workspace_markdown'" if where else "WHERE layer = 'workspace_markdown'"
            mems = _rows(conn, f"""
                SELECT agent_id, COUNT(DISTINCT id) AS memory_count, MAX(created_at) AS recent_activity
                FROM memories {where} {layer_clause} GROUP BY agent_id ORDER BY recent_activity DESC
            """, args)
            evs = _rows(conn, """
                SELECT observer_peer_id AS agent_id, COUNT(*) AS honcho_event_count,
                       MAX(created_at) AS recent_honcho_activity
                FROM honcho_events
                WHERE observer_peer_id IS NOT NULL
                GROUP BY observer_peer_id
            """)
        by = {r["agent_id"]: dict(r, honcho_event_count=0) for r in mems}
        for e in evs:
            if agent_id and e["agent_id"] != agent_id:
                continue
            item = by.setdefault(e["agent_id"], {"agent_id": e["agent_id"], "memory_count": 0, "recent_activity": None})
            item["honcho_event_count"] = e["honcho_event_count"]
            item["recent_honcho_activity"] = e["recent_honcho_activity"]
            item["recent_activity"] = max(filter(None, [item.get("recent_activity"), e["recent_honcho_activity"]]), default=None)
        return {"ok": True, "days": days, "agents": list(by.values())}

    def cross_agent_compare(self, agent_a: str, agent_b: str, query: str, limit: int = 10) -> dict[str, Any]:
        """Compare two agents' knowledge on a topic."""
        a = self.cross_agent_recall(query, agent_a, limit)["memories"]
        b = self.cross_agent_recall(query, agent_b, limit)["memories"]
        comparison = {"a_count": len(a), "b_count": len(b), "overlap_hint": "compare content fields for shared facts"}
        return {"ok": True, "agent_a": agent_a, "agent_b": agent_b, "query": query, "a_memories": a, "b_memories": b, "comparison": comparison}

    def list_agents(self) -> dict[str, Any]:
        """List all unique agent_ids."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            rows = _rows(conn, "SELECT DISTINCT agent_id FROM memories WHERE agent_id IS NOT NULL ORDER BY agent_id")
        return {"ok": True, "agents": [r["agent_id"] for r in rows]}


CROSS_AGENT_TOOLS = [
    {"name": "super_memory_cross_agent_recall", "description": "Query memories by agent", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "agent_id": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, "required": ["query", "agent_id"]}},
    {"name": "super_memory_cross_agent_honcho_ask", "description": "Query Honcho events by observer agent", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "observer_agent": {"type": "string"}, "about_peer": {"type": "string", "default": "boss"}, "limit": {"type": "integer", "default": 10}}, "required": ["query", "observer_agent"]}},
    {"name": "super_memory_cross_agent_summary", "description": "Agent activity summary", "inputSchema": {"type": "object", "properties": {"agent_id": {"type": "string"}, "days": {"type": "integer", "default": 30}}, "required": []}},
    {"name": "super_memory_cross_agent_compare", "description": "Compare two agents' knowledge", "inputSchema": {"type": "object", "properties": {"agent_a": {"type": "string"}, "agent_b": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "default": 10}}, "required": ["agent_a", "agent_b", "query"]}},
    {"name": "super_memory_list_agents", "description": "List all agent IDs", "inputSchema": {"type": "object", "properties": {}, "required": []}},
]
