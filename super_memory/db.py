"""Shared SQLite helpers for Super-Memory tools."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .config import load_config
from .migrations import run_migrations


class DBMixin:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.db_path = Path(self.config.workspace_root) / self.config.sqlite_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        run_migrations(self.config)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def _has(self, conn: sqlite3.Connection, table: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone() is not None


def validate_status(status: str) -> str:
    allowed = {"open", "claimed", "completed", "cancelled", "stale"}
    if status not in allowed:
        raise ValueError(f"invalid status: {status}")
    return status


def validate_agent_scope(agent_scope: str) -> tuple[str, str | None]:
    if agent_scope in {"current", "all"}:
        return (agent_scope, None)
    if agent_scope == "shared":
        return ("shared", None)
    if agent_scope.startswith("agent:"):
        agent = agent_scope.split(":", 1)[1].strip()
        if not agent or any(ch in agent for ch in "'\";()"):
            raise ValueError(f"invalid agent_scope: {agent_scope}")
        return ("agent", agent)
    raise ValueError(f"invalid agent_scope: {agent_scope}")


def validate_session_scope(session_scope: str) -> tuple[str, str | None]:
    if session_scope in {"recent", "all"}:
        return (session_scope, None)
    if session_scope.startswith("session:"):
        sid = session_scope.split(":", 1)[1].strip()
        if not sid or any(ch in sid for ch in "'\";()"):
            raise ValueError(f"invalid session_scope: {session_scope}")
        return ("session", sid)
    raise ValueError(f"invalid session_scope: {session_scope}")


def row_dicts(rows: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
