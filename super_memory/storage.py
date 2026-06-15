from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import MemoryRecord, MemoryType, SuperMemoryConfig


def sqlite_path(config: SuperMemoryConfig) -> Path:
    return Path(config.workspace_root) / config.sqlite_path


class SuperMemoryStore:
    def __init__(self, config: SuperMemoryConfig):
        self.config = config
        self.path = sqlite_path(config)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

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


def row_to_memory(row: sqlite3.Row) -> MemoryRecord:
    metadata = json.loads(row["metadata_json"])
    # Preserve pending_canonical_sync flag in metadata if present
    if "pending_canonical_sync" in row.keys() and row["pending_canonical_sync"]:
        metadata["pending_canonical_sync"] = True
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
