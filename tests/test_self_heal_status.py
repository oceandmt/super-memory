from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from super_memory.migrations import run_migrations
from super_memory.models import SuperMemoryConfig
from super_memory.self_heal import self_heal_status


def test_self_heal_status_counts_only_active_non_empty_missing_vectors(tmp_path: Path):
    cfg_path = tmp_path / "super-memory.yaml"
    cfg_path.write_text(
        f"workspace_root: {tmp_path}\n"
        "sqlite_path: data/test.sqlite3\n",
        encoding="utf-8",
    )
    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/test.sqlite3")
    run_migrations(cfg)
    db_path = Path(cfg.workspace_root) / cfg.sqlite_path
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_vectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT NOT NULL,
                layer TEXT NOT NULL,
                vector TEXT NOT NULL,
                provider TEXT,
                dimensions INTEGER,
                UNIQUE(memory_id, layer)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO memories
            (id, layer, content, type, scope, agent_id, tags_json, created_at, metadata_json)
            VALUES (?, ?, ?, 'context', 'session', 'lucas', '[]', '2026-01-01T00:00:00+00:00', ?)
            """,
            ("active-missing", "workspace_markdown", "active content needing vector", "{}"),
        )
        conn.execute(
            """
            INSERT INTO memories
            (id, layer, content, type, scope, agent_id, tags_json, created_at, metadata_json)
            VALUES (?, ?, ?, 'context', 'session', 'lucas', '[]', '2026-01-01T00:00:00+00:00', ?)
            """,
            ("active-empty", "workspace_markdown", "", "{}"),
        )
        conn.execute(
            """
            INSERT INTO memories
            (id, layer, content, type, scope, agent_id, tags_json, created_at, metadata_json)
            VALUES (?, ?, ?, 'context', 'session', 'lucas', '[]', '2026-01-01T00:00:00+00:00', ?)
            """,
            ("soft-deleted", "workspace_markdown", "soft deleted content", json.dumps({"soft_deleted": 1})),
        )
        conn.execute(
            """
            INSERT INTO memories
            (id, layer, content, type, scope, agent_id, tags_json, created_at, metadata_json)
            VALUES (?, ?, ?, 'context', 'session', 'lucas', '[]', '2026-01-01T00:00:00+00:00', ?)
            """,
            ("has-vector", "workspace_markdown", "already embedded", "{}"),
        )
        conn.execute(
            """
            INSERT INTO memory_vectors (memory_id, layer, vector, provider, dimensions)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("has-vector", "workspace_markdown", "[0.1, 0.2]", "test", 2),
        )
        conn.commit()

    status = self_heal_status(str(cfg_path))
    assert status["ok"] is True
    assert status["missing_vectors"] == 1
    assert status["eligible_memories"] == 2
    assert status["skipped_empty"] == 1
    assert status["skipped_soft_deleted"] == 1
