from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .models import MemoryRecord, MemoryType, SuperMemoryConfig


def sqlite_path(config: SuperMemoryConfig) -> Path:
    return Path(config.workspace_root) / config.sqlite_path


# ── Thread-safe connection cache ──────────────────────────────────────────────
_connection_cache: dict[str, sqlite3.Connection] = {}
_connection_lock = threading.Lock()


def _get_cached_connection(db_path: Path) -> sqlite3.Connection:
    """Return a cached SQLite connection for the given path.

    Creates a new connection on first access or if the cached connection
    becomes unusable (e.g. after fork, VACUUM, or unexpected close).
    All connections use WAL mode + busy_timeout + Row factory.
    """
    key = str(db_path.resolve())
    with _connection_lock:
        conn = _connection_cache.get(key)
        if conn is not None:
            try:
                conn.execute("SELECT 1")
                return conn
            except Exception:
                # Stale connection — close and recreate
                try:
                    conn.close()
                except Exception:
                    pass
                del _connection_cache[key]
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        _connection_cache[key] = conn
        return conn


def clear_connection_cache() -> None:
    """Close and clear all cached connections. Used by cleanup/VACUUM paths."""
    global _connection_cache
    with _connection_lock:
        for key, conn in _connection_cache.items():
            try:
                conn.close()
            except Exception:
                pass
        _connection_cache = {}


def invalidate_connection(db_path: Path) -> None:
    """Invalidate a specific cached connection (e.g. after VACUUM)."""
    key = str(db_path.resolve())
    with _connection_lock:
        conn = _connection_cache.pop(key, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


class SuperMemoryStore:
    def __init__(self, config: SuperMemoryConfig):
        self.config = config
        self.path = sqlite_path(config)

    def connect(self) -> sqlite3.Connection:
        """Get a cached SQLite connection with connection pooling."""
        return _get_cached_connection(self.path)

    def get_memory(self, memory_id: str, layer: str | None = None) -> MemoryRecord | None:
        params: list[str] = [memory_id]
        sql = "SELECT * FROM memories WHERE id = ?"
        if layer:
            sql += " AND layer = ?"
            params.append(layer)
        sql += " LIMIT 1"
        with self.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        if not row:
            return None
        return row_to_memory(row)

    def graph_neighbors(self, memory_id: str, direction: str = "out") -> list[sqlite3.Row]:
        if direction not in {"out", "in"}:
            raise ValueError(f"invalid graph direction: {direction}")
        column = "source_memory_id" if direction == "out" else "target_memory_id"
        sql = "SELECT * FROM graph_edges WHERE " + column + " = ?"
        with self.connect() as conn:
            return conn.execute(sql, (memory_id,)).fetchall()

    def list_memory_rows(self, limit: int = 100) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

    def get_pending_sync(self, layer: str) -> list[MemoryRecord]:
        """Return memories that have pending_canonical_sync for a given layer."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE layer = ? AND pending_canonical_sync = 1 ORDER BY created_at ASC",
                (layer,)
            ).fetchall()
        return [row_to_memory(r) for r in rows]

    def clear_pending_sync(self, memory_id: str, layer: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE memories SET pending_canonical_sync = 0 WHERE id = ? AND layer = ?",
                (memory_id, layer)
            )
            conn.commit()

    def _get_meta(self, key: str) -> str | None:
        """Get a runtime metadata value from the meta table.

        Uses a dedicated 'meta' table (created lazily) for small
        key-value persistence (e.g. depth prior state).
        Returns None if the meta table doesn't exist or key is missing.
        """
        with self.connect() as conn:
            try:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
            except Exception:
                return None
            row = conn.execute("SELECT value FROM _meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def _set_meta(self, key: str, value: object) -> None:
        """Set a runtime metadata value.

        Creates the meta table if needed. Value is JSON-serialized.
        """
        import json

        dumped = json.dumps(value, ensure_ascii=False)
        with self.connect() as conn:
            try:
                conn.execute("CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            except Exception:
                return
            conn.execute(
                "INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)",
                (key, dumped),
            )
            conn.commit()


def row_to_memory(row: sqlite3.Row) -> MemoryRecord:
    metadata = json.loads(row["metadata_json"])
    # Preserve pending_canonical_sync flag in metadata if present
    if "pending_canonical_sync" in row.keys() and row["pending_canonical_sync"]:
        metadata["pending_canonical_sync"] = True
    # Preserve content_hash in metadata for drift detection
    if "content_hash" in row.keys() and row["content_hash"]:
        metadata["content_hash"] = row["content_hash"]
    raw_type = row["type"]
    # Gracefully map legacy/invalid type values to a safe fallback so
    # consolidation and other bulk-read paths do not break on old data.
    valid_types = {t.value for t in MemoryType}
    if raw_type not in valid_types:
        metadata["original_type"] = raw_type
        raw_type = "context"
    return MemoryRecord(
        id=row["id"],
        content=row["content"],
        type=raw_type,
        scope=row["scope"],
        agent_id=row["agent_id"],
        session_id=row["session_id"],
        project=row["project"],
        tags=json.loads(row["tags_json"]),
        source=row["source"],
        trust_score=row["trust_score"],
        created_at=datetime.fromisoformat(row["created_at"]),
        metadata=metadata,
    )
