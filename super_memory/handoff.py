"""Handoff bundle creation and retrieval tools."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import load_config
from .db import validate_status


class HandoffTools:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.db_path = Path(self.config.workspace_root) / self.config.sqlite_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def ensure_tables(self) -> None:
        from .migrations import run_migrations
        run_migrations(self.config)
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS handoff_bundles (
                    id TEXT PRIMARY KEY,
                    from_agent TEXT,
                    to_agent TEXT,
                    session_id TEXT,
                    title TEXT,
                    summary TEXT,
                    context_json TEXT,
                    memory_ids_json TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    claimed_at TEXT,
                    completed_at TEXT
                )
            """)

    def _rows(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def _recent_memories(self, agent_id: str, query: str | None, limit: int) -> list[dict[str, Any]]:
        if query:
            sql = """
                SELECT id, content, type, agent_id, session_id, created_at FROM memories
                WHERE agent_id = ? AND content LIKE ? ORDER BY created_at DESC LIMIT ?
            """
            args = (agent_id, f"%{query}%", limit)
        else:
            sql = """
                SELECT id, content, type, agent_id, session_id, created_at FROM memories
                WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?
            """
            args = (agent_id, limit)
        return self._rows(sql, args)

    def create_handoff(
        self,
        from_agent: str,
        to_agent: str,
        title: str,
        summary: str,
        session_id: str | None = None,
        query: str | None = None,
        memory_limit: int = 10,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a handoff bundle with selected recent memories."""
        self.ensure_tables()
        memories = self._recent_memories(from_agent, query, memory_limit)
        memory_ids = [m["id"] for m in memories]
        payload = {"query": query, "memories": memories, **(context or {})}
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            bundle_id = conn.execute("SELECT lower(hex(randomblob(16)))").fetchone()[0]
            conn.execute("""
                INSERT INTO handoff_bundles
                (id, from_agent, to_agent, session_id, title, summary, context_json, memory_ids_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (bundle_id, from_agent, to_agent, session_id, title, summary,
                  json.dumps(payload), json.dumps(memory_ids)))
        return {"ok": True, "bundle_id": bundle_id, "memory_count": len(memories), "handoff": payload}

    def get_handoff(self, bundle_id: str) -> dict[str, Any]:
        """Retrieve a handoff bundle."""
        self.ensure_tables()
        rows = self._rows("SELECT * FROM handoff_bundles WHERE id = ?", (bundle_id,))
        if not rows:
            return {"ok": False, "error": "handoff_not_found", "bundle_id": bundle_id}
        row = rows[0]
        for key in ("context_json", "memory_ids_json"):
            try:
                row[key[:-5] if key.endswith("_json") else key] = json.loads(row.get(key) or "null")
            except json.JSONDecodeError:
                row[key[:-5]] = row.get(key)
        return {"ok": True, "bundle": row}

    def list_handoffs(self, to_agent: str | None = None, status: str | None = None, limit: int = 20) -> dict[str, Any]:
        """List handoff bundles."""
        self.ensure_tables()
        clauses, args = [], []
        if to_agent:
            clauses.append("to_agent = ?")
            args.append(to_agent)
        if status:
            clauses.append("status = ?")
            args.append(status)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._rows(f"""
            SELECT id, from_agent, to_agent, session_id, title, summary, status, created_at
            FROM handoff_bundles {where} ORDER BY created_at DESC LIMIT ?
        """, tuple(args + [limit]))
        return {"ok": True, "handoffs": rows, "count": len(rows)}

    def update_handoff_status(self, bundle_id: str, status: str) -> dict[str, Any]:
        """Mark a handoff as open, claimed, or completed."""
        validate_status(status)
        self.ensure_tables()
        column_map = {"claimed": "claimed_at", "completed": "completed_at"}
        column = column_map.get(status)
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            if column:
                cur = conn.execute("UPDATE handoff_bundles SET status = ?, " + column + " = CURRENT_TIMESTAMP WHERE id = ?", (status, bundle_id))
            else:
                cur = conn.execute("UPDATE handoff_bundles SET status = ? WHERE id = ?", (status, bundle_id))
        return {"ok": cur.rowcount > 0, "bundle_id": bundle_id, "status": status}

    def auto_handoff_on_spawn(self, from_agent: str, to_agent: str, objective: str, constraints: dict[str, Any] | str | None = None, session_id: str | None = None, context_files: list[str] | None = None, memory_limit: int = 10) -> dict[str, Any]:
        ctx = {"objective": objective, "constraints": constraints or {}, "context_files": {}}
        for fp in context_files or []:
            try:
                ctx["context_files"][fp] = Path(fp).read_text(encoding="utf-8")[:4000]
            except Exception as exc:
                ctx["context_files"][fp] = f"unreadable: {exc}"
        return self.create_handoff(from_agent, to_agent, f"Spawn handoff: {objective[:80]}", objective, session_id, objective, memory_limit, ctx)

    def load_current_handoff(self, agent_id: str) -> dict[str, Any]:
        self.ensure_tables()
        rows = self._rows(
            "SELECT id FROM handoff_bundles WHERE to_agent=? AND status='open'"
            " ORDER BY created_at DESC LIMIT 1",
            (agent_id,),
        )
        if not rows:
            return {"ok": False, "error": "no_open_handoff", "agent_id": agent_id}
        out = self.get_handoff(rows[0]["id"])
        self.update_handoff_status(rows[0]["id"], "claimed")
        return out

    def complete_handoff_with_outcome(self, bundle_id: str, outcome_summary: str, created_artifacts_json: str | list | dict | None = None, proof_status: str = "unknown") -> dict[str, Any]:
        self.ensure_tables()
        artifacts = created_artifacts_json
        if isinstance(artifacts, str):
            try:
                artifacts = json.loads(artifacts)
            except json.JSONDecodeError:
                artifacts = [artifacts]
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.row_factory = sqlite3.Row
            bundle = conn.execute("SELECT * FROM handoff_bundles WHERE id=?", (bundle_id,)).fetchone()
            if not bundle:
                return {"ok": False, "error": "handoff_not_found", "bundle_id": bundle_id}
            conn.execute("UPDATE handoff_bundles SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE id=?", (bundle_id,))
            mem_id = conn.execute("SELECT lower(hex(randomblob(16)))").fetchone()[0]
            now = conn.execute("SELECT datetime('now')").fetchone()[0]
            tags = json.dumps(["agent:" + str(bundle["to_agent"]), "scope:project", "type:handoff_outcome"])
            meta = json.dumps({"bundle_id": bundle_id, "artifacts": artifacts, "proof_status": proof_status})
            conn.execute("""
                INSERT OR IGNORE INTO memories
                (id, layer, content, type, scope, agent_id, session_id, project, tags_json, source, trust_score, created_at, metadata_json)
                VALUES (?, 'workspace_markdown', ?, 'handoff_outcome', 'project', ?, ?, NULL, ?, 'handoff_outcome', 0.8, ?, ?)
            """, (mem_id, outcome_summary, bundle["to_agent"], bundle["session_id"], tags, now, meta))
            ev_id = conn.execute("SELECT lower(hex(randomblob(16)))").fetchone()[0]
            conn.execute("""
                INSERT INTO honcho_events
                (id, memory_id, workspace, session_id, observer_peer_id, observed_peer_id, content, source, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ev_id, mem_id, "openclaw", bundle["session_id"], bundle["to_agent"], bundle["from_agent"], outcome_summary, "handoff_outcome", meta, now))
        return {"ok": True, "bundle_id": bundle_id, "memory_id": mem_id, "proof_status": proof_status}


HANDOFF_TOOLS = [
    {"name": "super_memory_create_handoff", "description": "Create an agent handoff bundle", "inputSchema": {"type": "object", "properties": {"from_agent": {"type": "string"}, "to_agent": {"type": "string"}, "title": {"type": "string"}, "summary": {"type": "string"}, "session_id": {"type": "string"}, "query": {"type": "string"}, "memory_limit": {"type": "integer", "default": 10}, "context": {"type": "object"}}, "required": ["from_agent", "to_agent", "title", "summary"]}},
    {"name": "super_memory_get_handoff", "description": "Retrieve a handoff bundle", "inputSchema": {"type": "object", "properties": {"bundle_id": {"type": "string"}}, "required": ["bundle_id"]}},
    {"name": "super_memory_list_handoffs", "description": "List handoff bundles", "inputSchema": {"type": "object", "properties": {"to_agent": {"type": "string"}, "status": {"type": "string"}, "limit": {"type": "integer", "default": 20}}, "required": []}},
    {"name": "super_memory_update_handoff_status", "description": "Update handoff status", "inputSchema": {"type": "object", "properties": {"bundle_id": {"type": "string"}, "status": {"type": "string"}}, "required": ["bundle_id", "status"]}},
    {"name": "super_memory_auto_handoff_on_spawn", "description": "Create a spawn handoff with extra context", "inputSchema": {"type": "object", "properties": {"from_agent": {"type": "string"}, "to_agent": {"type": "string"}, "objective": {"type": "string"}, "constraints": {"type": "object"}, "session_id": {"type": "string"}, "context_files": {"type": "array", "items": {"type": "string"}}, "memory_limit": {"type": "integer", "default": 10}}, "required": ["from_agent", "to_agent", "objective"]}},
    {"name": "super_memory_load_current_handoff", "description": "Load latest open handoff for an agent", "inputSchema": {"type": "object", "properties": {"agent_id": {"type": "string"}}, "required": ["agent_id"]}},
    {"name": "super_memory_complete_handoff_with_outcome", "description": "Complete handoff and record outcome", "inputSchema": {"type": "object", "properties": {"bundle_id": {"type": "string"}, "outcome_summary": {"type": "string"}, "created_artifacts_json": {}, "proof_status": {"type": "string", "default": "unknown"}}, "required": ["bundle_id", "outcome_summary"]}},
]
