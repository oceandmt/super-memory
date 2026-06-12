from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import MemoryRecord, SuperMemoryConfig


def sqlite_path(config: SuperMemoryConfig) -> Path:
    return Path(config.workspace_root) / config.sqlite_path


class SuperMemoryStore:
    def __init__(self, config: SuperMemoryConfig):
        self.config = config
        self.path = sqlite_path(config)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_memory(self, memory_id: str, layer: str | None = None) -> MemoryRecord | None:
        where = "id = ?"
        params: list[str] = [memory_id]
        if layer:
            where += " AND layer = ?"
            params.append(layer)
        with self.connect() as conn:
            row = conn.execute(f"SELECT * FROM memories WHERE {where} LIMIT 1", params).fetchone()
        if not row:
            return None
        return row_to_memory(row)

    def graph_neighbors(self, memory_id: str, direction: str = "out") -> list[sqlite3.Row]:
        column = "source_memory_id" if direction == "out" else "target_memory_id"
        with self.connect() as conn:
            return conn.execute(f"SELECT * FROM graph_edges WHERE {column} = ?", (memory_id,)).fetchall()

    def list_memory_rows(self, limit: int = 100) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()


def row_to_memory(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"],
        content=row["content"],
        type=row["type"],
        scope=row["scope"],
        agent_id=row["agent_id"],
        session_id=row["session_id"],
        project=row["project"],
        tags=json.loads(row["tags_json"]),
        source=row["source"],
        trust_score=row["trust_score"],
        created_at=datetime.fromisoformat(row["created_at"]),
        metadata=json.loads(row["metadata_json"]),
    )
