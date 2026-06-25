from __future__ import annotations

import sqlite3

from super_memory import bridge
from super_memory.config import load_config


def test_remember_creates_workspace_markdown_sqlite_row():
    import uuid
    result = bridge.remember({
        "content": f"cross layer health unit test {uuid.uuid4().hex[:12]}",
        "type": "context",
        "scope": "session",
        "source": "test.cross_layer_health",
    })
    memory_id = result["record"]["id"]

    cfg = load_config(None)
    db_path = cfg.workspace_root / cfg.sqlite_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        layers = [
            row["layer"]
            for row in conn.execute(
                "SELECT layer FROM memories WHERE id = ? ORDER BY layer",
                (memory_id,),
            ).fetchall()
        ]
        assert set(layers) == {"workspace_markdown", "mempalace", "honcho", "neural_memory"}

        hashes = [
            row["content_hash"]
            for row in conn.execute(
                "SELECT content_hash FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchall()
        ]
        assert len(set(hashes)) == 1
        assert hashes[0]
    finally:
        conn.close()


def test_cross_layer_health_endpoint_shape():
    health = bridge.cross_layer_health()
    assert "ok" in health
    assert "verdict" in health
    assert "full_4layer_coverage" in health
    assert "sqlite_only_ids" in health
    assert "content_drift_count" in health
    assert "orphan_projections_total" in health
