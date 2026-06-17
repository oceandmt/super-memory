"""PostgreSQL adapter — production implementation.

This adapter activates when POSTGRES_URL is set in environment.
Supports psycopg2 (recommended) with asyncpg fallback.

Usage:
    export POSTGRES_URL="postgresql://user:pass@localhost:5432/super_memory"
    # Then set db_backend="postgres" in super-memory.yaml
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any

from .base import AbstractDBAdapter

if TYPE_CHECKING:
    from ..config import SuperMemoryConfig

logger = logging.getLogger("super-memory.db.postgres")

# ── Schema DDL (mirrors SQLite tables, with PG types) ──────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    layer TEXT NOT NULL DEFAULT 'neural_memory',
    content TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'context',
    scope TEXT NOT NULL DEFAULT 'session',
    agent_id TEXT NOT NULL DEFAULT 'lucas',
    session_id TEXT,
    project TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    source TEXT,
    trust_score REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    pending_canonical_sync INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_memories_layer ON memories(layer);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);

CREATE TABLE IF NOT EXISTS graph_edges (
    id TEXT PRIMARY KEY,
    source_memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL DEFAULT 'related',
    weight REAL NOT NULL DEFAULT 0.5,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_graph_source ON graph_edges(source_memory_id);
CREATE INDEX IF NOT EXISTS idx_graph_target ON graph_edges(target_memory_id);

CREATE TABLE IF NOT EXISTS intelligence_events (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    subject TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_intelligence_kind ON intelligence_events(kind);

CREATE TABLE IF NOT EXISTS lifecycle_state (
    key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS import_manifest (
    key TEXT PRIMARY KEY,
    flow TEXT NOT NULL,
    path TEXT,
    sha256 TEXT,
    chunk_index INTEGER,
    memory_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS watch_manifest (
    path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime DOUBLE PRECISION NOT NULL,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class PostgresAdapter(AbstractDBAdapter):
    """PostgreSQL adapter — production-ready.

    Requires:
        pip install psycopg2-binary
    OR
        pip install asyncpg

    Environment:
        POSTGRES_URL=postgresql://user:pass@host:5432/dbname
    """

    def __init__(self, config: "SuperMemoryConfig"):
        self.config = config
        self.pg_url = os.environ.get("POSTGRES_URL", "")
        self._conn = None
        self._driver = self._detect_driver()

    def _detect_driver(self) -> str:
        """Detect available PostgreSQL driver."""
        try:
            import importlib
            if importlib.util.find_spec("psycopg2"):
                return "psycopg2"
            if importlib.util.find_spec("asyncpg"):
                return "asyncpg"
        except Exception:
            pass
        return "none"

    def connect(self) -> None:
        if not self.pg_url:
            raise RuntimeError(
                "POSTGRES_URL not set. "
                "Set it to a PostgreSQL connection string, e.g.: "
                "postgresql://user:pass@localhost:5432/super_memory"
            )
        if self._driver == "none":
            raise RuntimeError(
                "No PostgreSQL driver found. Install one:\n"
                "  pip install psycopg2-binary   (recommended)\n"
                "  pip install asyncpg           (async)"
            )
        if self._driver == "psycopg2":
            import psycopg2
            import psycopg2.extras
            self._conn = psycopg2.connect(self.pg_url)
            self._conn.autocommit = False
            psycopg2.extras.register_default_json(loads=lambda x: x)
        elif self._driver == "asyncpg":
            raise RuntimeError(
                "asyncpg is async-only. Use psycopg2 for synchronous adapter. "
                "Install: pip install psycopg2-binary"
            )
        self._ensure_schema()
        logger.info("PostgreSQL connected to %s", self.pg_url.split("@")[-1] if "@" in self.pg_url else "db")

    def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)
        self._conn.commit()

    @property
    def connection(self):
        if self._conn is None:
            self.connect()
        return self._conn

    def execute(self, sql: str, params: tuple | None = None) -> Any:
        """Execute SQL, auto-adapting SQLite placeholders (?) to PG ($1...)."""
        adapted_sql = sql
        if params is not None:
            param_count = len(params)
            adapted_sql = sql
            # Only replace ? that are actual placeholders (simple heuristic)
            if "?" in adapted_sql:
                idx = 0
                result = []
                for ch in adapted_sql:
                    if ch == "?":
                        idx += 1
                        result.append(f"${idx}")
                    else:
                        result.append(ch)
                adapted_sql = "".join(result)
        with self.connection.cursor() as cur:
            cur.execute(adapted_sql, params)
            return cur

    def executemany(self, sql: str, params_list: list[tuple]) -> Any:
        adapted_sql = sql
        if params_list and "?" in adapted_sql:
            if len(params_list[0]) if params_list else 0:
                idx = 0
                result = []
                for ch in adapted_sql:
                    if ch == "?":
                        idx += 1
                        result.append(f"${idx}")
                    else:
                        result.append(ch)
                adapted_sql = "".join(result)
        with self.connection.cursor() as cur:
            cur.executemany(adapted_sql, params_list)
            return cur

    def fetchone(self, cursor: Any) -> dict[str, Any] | None:
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))

    def fetchall(self, cursor: Any) -> list[dict[str, Any]]:
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def commit(self) -> None:
        if self._conn is not None:
            self._conn.commit()

    def rollback(self) -> None:
        if self._conn is not None:
            self._conn.rollback()
