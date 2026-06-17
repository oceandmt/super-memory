"""SQLite database adapter (default)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .base import AbstractDBAdapter

if TYPE_CHECKING:
    from ..config import SuperMemoryConfig


class SQLiteAdapter(AbstractDBAdapter):
    """SQLite adapter wrapping the existing sqlite3 code.

    This is the default backend. It mirrors the existing connection
    patterns with WAL mode, busy timeout, and row_factory setup.
    """

    def __init__(self, config: "SuperMemoryConfig"):
        self.config = config
        self.path = Path(config.workspace_root) / config.sqlite_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(str(self.path), timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.row_factory = sqlite3.Row

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn  # type: ignore[return-value]

    def execute(self, sql: str, params: tuple | None = None) -> sqlite3.Cursor:
        if params is None:
            return self.connection.execute(sql)
        return self.connection.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        return self.connection.executemany(sql, params_list)

    def fetchone(self, cursor: sqlite3.Cursor) -> dict[str, Any] | None:
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self, cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
        return [dict(r) for r in cursor.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()
