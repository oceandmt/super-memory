"""SQLite storage layer: connection pooling, FTS5 tables, memory CRUD.

Key services:
- SuperMemoryStore: thread-safe connection cache with WAL mode
- FTS5 tables: memories_fts, honcho_events_fts for text search
- row_to_memory() helper: sqlite3.Row → MemoryRecord
- Connection invalidation/clear for VACUUM safety
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import weakref
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from .models import MemoryRecord, MemoryType, SuperMemoryConfig


def sqlite_path(config: SuperMemoryConfig) -> Path:
    return Path(config.workspace_root) / config.sqlite_path


# ── Thread-safe connection cache ──────────────────────────────────────────────


class _ThreadConnections:
    """Connections owned by one thread.

    The holder is stored in ``threading.local()``.  When a short-lived thread
    exits, its holder is released and ``__del__`` closes the SQLite handles.
    The process-wide registry is weak so it does not keep dead threads (and
    their file descriptors) alive, while still allowing explicit shutdown and
    path invalidation to close handles owned by live threads.
    """

    def __init__(self) -> None:
        self._connections: dict[str, sqlite3.Connection] = {}
        self._lock = threading.RLock()
        self._owner_ref = weakref.ref(threading.current_thread())

    def owner_alive(self) -> bool:
        owner = self._owner_ref()
        return bool(owner is not None and owner.is_alive())

    def get(self, path: str) -> sqlite3.Connection | None:
        with self._lock:
            return self._connections.get(path)

    def set(self, path: str, conn: sqlite3.Connection) -> None:
        with self._lock:
            self._connections[path] = conn

    def pop(self, path: str) -> sqlite3.Connection | None:
        with self._lock:
            return self._connections.pop(path, None)

    def close(self, path: str | None = None) -> None:
        with self._lock:
            if path is None:
                connections = list(self._connections.values())
                self._connections.clear()
            else:
                conn = self._connections.pop(path, None)
                connections = [conn] if conn is not None else []
        for conn in connections:
            with suppress(Exception):
                conn.close()

    def count(self) -> int:
        with self._lock:
            return len(self._connections)

    def reset_lock_after_fork(self) -> None:
        """Replace a lock that may be owned by a vanished parent thread."""
        self._lock = threading.RLock()

    def __del__(self) -> None:
        # Thread-local values are released when their owning thread exits.
        # Keep finalization best-effort because interpreter shutdown may have
        # already torn down parts of sqlite3.
        with suppress(Exception):
            self.close()


_connection_lock = threading.RLock()
_connection_local = threading.local()
_connection_holders: weakref.WeakSet[_ThreadConnections] = weakref.WeakSet()
_connection_pid = os.getpid()


def _reset_in_child_after_fork() -> None:
    """Make an inherited lock safe; handles are closed lazily on first use."""
    global _connection_lock, _connection_pid
    _connection_lock = threading.RLock()
    _connection_pid = -1


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_in_child_after_fork)


def _ensure_current_process() -> None:
    """Discard SQLite handles inherited from a parent process."""
    global _connection_lock, _connection_local, _connection_holders, _connection_pid
    pid = os.getpid()
    if pid == _connection_pid:
        return

    # A lock held by a vanished parent thread can never be released in the
    # child.  Replacing it before acquisition is safe because a PID change only
    # happens after fork, where the child has one surviving thread.
    _connection_lock = threading.RLock()
    with _connection_lock:
        if pid == _connection_pid:
            return
        inherited_holders = list(_connection_holders)
        for holder in inherited_holders:
            holder.reset_lock_after_fork()
            holder.close()
        _connection_local = threading.local()
        _connection_holders = weakref.WeakSet()
        _connection_pid = pid


def _current_thread_connections() -> _ThreadConnections:
    holder = getattr(_connection_local, "connections", None)
    if holder is None:
        holder = _ThreadConnections()
        _connection_local.connections = holder
        _connection_holders.add(holder)
    return holder


# Micro-gap 6: Read-only recovery constants
_MAX_RECONNECT_ATTEMPTS = 3
_RECONNECT_BACKOFF_MS = [100, 500, 2000]  # progressive delays
_recovery_state: dict[str, dict] = {}


def _get_cached_connection(db_path: Path) -> sqlite3.Connection:
    """Return a cached SQLite connection for the given path.

    Creates a new connection on first access or if the cached connection
    becomes unusable (e.g. after fork, VACUUM, or unexpected close).
    All connections use WAL mode + busy_timeout + Row factory.

    Micro-gap 6: Read-only recovery — auto-reconnect with backoff.
    """
    # E9: each thread gets its own connection. A single shared connection with
    # check_same_thread=False risks interleaved transactions across threads.
    # Thread-local holders preserve that isolation without retaining completed
    # threads forever in a process-global dictionary.
    _ensure_current_process()
    key = str(db_path.resolve())
    with _connection_lock:
        holder = _current_thread_connections()
        conn = holder.get(key)
        if conn is not None:
            try:
                conn.execute("SELECT 1")
                return conn
            except Exception:
                holder.pop(key)
                with suppress(Exception):
                    conn.close()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        holder.set(key, conn)
        return conn


# ── Micro-gap 6: Read-only Recovery ────────────────────────────────────
# Mirrors memory-core manager.readonly-recovery.test.ts:
#   auto-reconnect on DB failure, progressive backoff


def get_recovery_state(db_path: str | Path) -> dict:
    """Get recovery state for a given db path."""
    return _recovery_state.get(str(db_path), {"attempts": 0, "last_error": "", "recovered": False})


def set_recovery_state(db_path: str | Path, state: dict) -> None:
    """Set recovery state for a given db path."""
    _recovery_state[str(db_path)] = state


def attempt_readonly_recovery(db_path: Path, error: Exception) -> dict:
    """Attempt recovery from a database connection error.

    Progressive backoff: 100ms, 500ms, 2s.
    After max attempts, marks as permanent failure.

    Args:
        db_path: Path to the database file.
        error: The exception that triggered recovery.

    Returns:
        Dict with recovery status.
    """
    key = str(db_path.resolve())
    state = _recovery_state.get(key, {"attempts": 0, "last_error": "", "recovered": False})
    
    if state.get("attempts", 0) >= _MAX_RECONNECT_ATTEMPTS:
        return {"recovered": False, "attempts": state["attempts"], "error": str(error), "permanent": True}
    
    attempt = state.get("attempts", 0) + 1
    delay_ms = _RECONNECT_BACKOFF_MS[min(attempt - 1, len(_RECONNECT_BACKOFF_MS) - 1)]
    
    import time as _time
    _time.sleep(delay_ms / 1000)
    
    # Invalidate stale connection
    invalidate_connection(db_path)
    
    # Try to reconnect
    try:
        new_conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
        new_conn.execute("SELECT 1")
        new_conn.close()
        _recovery_state[key] = {"attempts": attempt, "last_error": "", "recovered": True, "last_recovery": _time.time()}
        return {"recovered": True, "attempts": attempt, "delay_ms": delay_ms}
    except Exception as exc:
        _recovery_state[key] = {"attempts": attempt, "last_error": str(exc), "recovered": False}
        return {"recovered": False, "attempts": attempt, "delay_ms": delay_ms, "error": str(exc)}


def recovery_status(db_path: str | None = None) -> dict:
    """Get recovery status for all or specified db.

    Returns:
        Dict with recovery state.
    """
    if db_path:
        return get_recovery_state(db_path)
    return {
        "entries": len(_recovery_state),
        "states": {k: v for k, v in _recovery_state.items()},
    }


def reset_recovery_state(db_path: str | None = None) -> dict:
    """Reset recovery state."""
    if db_path:
        _recovery_state.pop(str(db_path), None)
    else:
        _recovery_state.clear()
    return {"ok": True, "reset": True}


def close_current_thread_connections(db_path: str | Path | None = None) -> None:
    """Close cached connections owned by the calling thread.

    If ``db_path`` is supplied, only the connection for that database is
    closed.  This is the normal per-store/request teardown hook.
    """
    _ensure_current_process()
    path = str(Path(db_path).resolve()) if db_path is not None else None
    with _connection_lock:
        holder = getattr(_connection_local, "connections", None)
        if holder is not None:
            holder.close(path)


def close_all_connections() -> None:
    """Close every cached connection in this process (shutdown/test hook)."""
    _ensure_current_process()
    with _connection_lock:
        for holder in list(_connection_holders):
            holder.close()


def clear_connection_cache() -> None:
    """Backward-compatible close-all hook used by cleanup/VACUUM paths."""
    close_all_connections()


def connection_cache_size() -> int:
    """Return the number of live cached handles (primarily for diagnostics)."""
    _ensure_current_process()
    with _connection_lock:
        holders = list(_connection_holders)
        # Some Python runtimes retain a dead Thread object's local dictionary
        # until later GC. Reap those holders deterministically for diagnostics
        # and file-descriptor safety; connections use check_same_thread=False.
        for holder in holders:
            if not holder.owner_alive():
                holder.close()
        return sum(holder.count() for holder in list(_connection_holders))


def invalidate_connection(db_path: Path) -> None:
    """Invalidate cached connections for a path across all threads (e.g. after VACUUM)."""
    _ensure_current_process()
    path = str(db_path.resolve())
    with _connection_lock:
        for holder in list(_connection_holders):
            holder.close(path)


class SuperMemoryStore:
    def __init__(self, config: SuperMemoryConfig):
        self.config = config
        self.path = sqlite_path(config)

    def connect(self) -> sqlite3.Connection:
        """Get a cached SQLite connection with connection pooling."""
        return _get_cached_connection(self.path)

    def close(self) -> None:
        """Close this store's connection in the calling thread."""
        close_current_thread_connections(self.path)

    @staticmethod
    def close_all() -> None:
        """Close all store connections in this process for shutdown/tests."""
        close_all_connections()

    def get_memory(self, memory_id: str, layer: str | None = None, include_deleted: bool = False) -> MemoryRecord | None:
        params: list[str] = [memory_id]
        sql = "SELECT * FROM memories WHERE id = ?"
        if layer:
            sql += " AND layer = ?"
            params.append(layer)
        if not include_deleted:
            from .models import ALIVE_SQL
            sql += " AND " + ALIVE_SQL
        sql += " ORDER BY CASE WHEN layer = 'workspace_markdown' THEN 0 ELSE 1 END, created_at DESC LIMIT 1"
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

    def list_memory_rows(self, limit: int = 100, include_deleted: bool = False) -> list[sqlite3.Row]:
        # E25: this primitive feeds consolidate_real (dedup/contradictions/
        # promotions), context(), graph projection and cognitive. Without a
        # soft-delete guard, forgotten memories re-entered all of those --
        # e.g. consolidation reported contradictions whose 'side A' was an
        # already-forgotten record. Exclude soft-deleted by default; callers
        # that truly need every row (raw maintenance/repair) pass
        # include_deleted=True.
        with self.connect() as conn:
            if include_deleted:
                return conn.execute(
                    "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return conn.execute(
                "SELECT * FROM memories "
                "WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1 "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

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
