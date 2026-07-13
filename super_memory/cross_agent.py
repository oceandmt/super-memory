"""Cross-agent memory query and comparison tools."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import load_config

__all__ = ["CROSS_AGENT_TOOLS", "CrossAgentTools"]


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


def _pseudo_semantic_score(query: str, content: str) -> float:
    """Return deterministic semantic-ish score without external embeddings.

    Cross-agent recall should be useful out-of-the-box, even when sqlite-vec,
    Ollama, OpenAI, or other embedding providers are not configured.  This
    fallback blends exact phrase overlap, token coverage, and character n-gram
    similarity so FTS/LIKE candidates are semantically reordered by default.
    """
    import math
    import re

    q = (query or "").lower().strip()
    c = (content or "").lower().strip()
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0

    phrase = 0.6 if q in c else 0.0
    q_terms = [t for t in re.split(r"[^a-zA-Z0-9_]+", q) if len(t) > 1]
    c_terms = [t for t in re.split(r"[^a-zA-Z0-9_]+", c) if len(t) > 1]
    token_score = 0.0
    if q_terms and c_terms:
        counts: dict[str, int] = {}
        for term in c_terms:
            counts[term] = counts.get(term, 0) + 1
        coverage = sum(1 for term in set(q_terms) if term in counts) / max(1, len(set(q_terms)))
        tf = sum((1 + math.log(1 + counts.get(term, 0))) for term in set(q_terms) if term in counts)
        token_score = min(1.0, coverage * 0.75 + tf / max(10.0, len(c_terms)) * 0.25)

    q_grams = {q[i:i + 3] for i in range(max(0, len(q) - 2))}
    c_grams = {c[i:i + 3] for i in range(max(0, len(c) - 2))}
    gram_score = len(q_grams & c_grams) / max(1, len(q_grams | c_grams)) if q_grams and c_grams else 0.0
    return min(1.0, phrase * 0.45 + token_score * 0.40 + gram_score * 0.15)


class CrossAgentTools:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.db_path = Path(self.config.workspace_root) / self.config.sqlite_path

    def _fts_search(self, conn: sqlite3.Connection, query: str, agent_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Try FTS5 search first; fall back to LIKE."""
        try:
            # Check if FTS table exists
            has_fts = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memories_fts'"
            ).fetchone() is not None
            if has_fts:
                # Build FTS query from user query (tokenize words)
                fts_words = ' '.join(w for w in query.split() if len(w) > 1)
                if fts_words:
                    rows = _rows(conn, """
                        SELECT m.id, m.layer, m.content, m.type, m.scope, m.agent_id,
                               m.session_id, m.project, m.tags_json, m.source,
                               m.trust_score, m.created_at, m.metadata_json,
                               rank as fts_score
                        FROM memories m
                        JOIN memories_fts fts ON m.rowid = fts.rowid
                        WHERE m.agent_id = ? AND m.layer = 'workspace_markdown'
                          AND memories_fts MATCH ?
                          AND COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0) != 1
                        ORDER BY rank ASC, m.created_at DESC
                        LIMIT ?
                    """, (agent_id, fts_words, limit))
                    if rows:
                        return rows
        except Exception:
            pass
        return []

    def cross_agent_recall(self, query: str, agent_id: str, limit: int = 10, semantic_reorder: bool = True) -> dict[str, Any]:
        """Query memories filtered by agent_id with FTS5 fallback.

        ``semantic_reorder=True`` is the default so cross-agent memory feels
        semantic by default.  The reorder stage is deterministic and local; it
        does not require external embedding providers or network calls.
        """
        like = f"%{query}%"
        candidate_limit = limit * 2 if semantic_reorder else limit
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")

            # Try FTS5 first
            rows = self._fts_search(conn, query, agent_id, candidate_limit)
            if not rows:
                # Fallback to LIKE
                rows = _rows(conn, """
                    SELECT id, layer, content, type, scope, agent_id, session_id, project,
                           tags_json, source, trust_score, created_at, metadata_json
                    FROM memories
                    WHERE agent_id = ? AND content LIKE ? AND layer = 'workspace_markdown'
                      AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1
                    ORDER BY created_at DESC LIMIT ?
                """, (agent_id, like, candidate_limit))
        memories = [_decode(r) for r in rows]
        if semantic_reorder:
            for memory in memories:
                memory["_semantic_score"] = _pseudo_semantic_score(query, memory.get("content") or "")
            memories.sort(key=lambda memory: memory.get("_semantic_score", 0.0), reverse=True)
            memories = memories[:limit]
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
            aid = e["agent_id"]
            if aid in by:
                by[aid]["honcho_event_count"] = e["honcho_event_count"]
            elif not agent_id:
                by[aid] = {"agent_id": aid, "memory_count": 0, "recent_activity": None, "honcho_event_count": e["honcho_event_count"]}
        return {"ok": True, "days": days, "agents": sorted(by.values(), key=lambda x: (x.get("recent_activity") or "", int(x.get("honcho_event_count") or 0)), reverse=True)}

    def cross_agent_compare(self, agent_a: str = "lucas", agent_b: str = "alex", limit: int = 5) -> dict[str, Any]:
        """Compare two agents' memory overlap."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            only_a = _rows(conn, """
                SELECT id, content, type, created_at FROM memories
                WHERE agent_id = ? AND layer = 'workspace_markdown'
                ORDER BY created_at DESC LIMIT ?
            """, (agent_a, limit))
            only_b = _rows(conn, """
                SELECT id, content, type, created_at FROM memories
                WHERE agent_id = ? AND layer = 'workspace_markdown'
                ORDER BY created_at DESC LIMIT ?
            """, (agent_b, limit))
            overlap = _rows(conn, """
                SELECT DISTINCT ma.content AS content_a, mb.content AS content_b,
                       ma.type, ma.created_at
                FROM memories ma JOIN memories mb ON ma.content = mb.content
                WHERE ma.agent_id = ? AND mb.agent_id = ? AND ma.layer = 'workspace_markdown'
                LIMIT ?
            """, (agent_a, agent_b, limit))
        return {"ok": True, "agent_a": {"agent_id": agent_a, "recent": only_a}, "agent_b": {"agent_id": agent_b, "recent": only_b}, "overlapping": overlap, "overlap_count": len(overlap)}


CROSS_AGENT_TOOLS = [
    {
        "name": "super_memory_cross_agent_recall",
        "description": "Query memories from a specific agent",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "agent_id": {"type": "string", "default": "lucas"},
                "limit": {"type": "integer", "default": 10},
                "semantic_reorder": {"type": "boolean", "default": True},
            },
            "required": ["query"],
        },
    },
    {
        "name": "super_memory_cross_agent_honcho_ask",
        "description": "Ask about another agent's honcho events",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "observer_agent": {"type": "string", "default": "lucas"},
                "about_peer": {"type": "string", "default": "boss"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "super_memory_cross_agent_summary",
        "description": "Summary of agents and their memory counts",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "days": {"type": "integer", "default": 30},
            },
        },
    },
    {
        "name": "super_memory_cross_agent_compare",
        "description": "Compare two agents' memory overlap",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_a": {"type": "string", "default": "lucas"},
                "agent_b": {"type": "string", "default": "alex"},
                "limit": {"type": "integer", "default": 5},
            },
        },
    },
]
