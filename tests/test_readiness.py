from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from super_memory import bridge
from super_memory.api import app


def _config(tmp_path: Path, *, canonical_first: bool = True) -> Path:
    cfg = tmp_path / "super-memory.yaml"
    cfg.write_text(
        "\n".join(
            [
                f'workspace_root: "{tmp_path}"',
                "sqlite_path: data/test.sqlite3",
                f"require_canonical_first: {str(canonical_first).lower()}",
                "vector_enabled: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return cfg


def _database(tmp_path: Path, *, pending: int = 0, omit_layer: str | None = None) -> Path:
    path = tmp_path / "data" / "test.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE memories (
                id TEXT NOT NULL,
                layer TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                pending_canonical_sync INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (id, layer)
            )
            """
        )
        for layer in ("workspace_markdown", "mempalace", "honcho", "neural_memory"):
            if layer == omit_layer:
                continue
            conn.execute(
                "INSERT INTO memories(id, layer, content, pending_canonical_sync) VALUES(?,?,?,?)",
                ("memory-1", layer, "readiness evidence", pending if layer == "mempalace" else 0),
            )
    return path


def test_missing_database_is_not_created_and_blocks_readiness(tmp_path: Path):
    cfg = _config(tmp_path)
    db_path = tmp_path / "data" / "test.sqlite3"

    result = bridge.health(config_path=str(cfg))

    assert result["ok"] is True  # liveness compatibility
    assert result["ready"] is False
    assert result["blocking"] == ["database"]
    assert result["checks"]["database"]["reason"] == "database_missing"
    assert not db_path.exists()


def test_healthy_database_is_ready_without_mutating_it(tmp_path: Path):
    cfg = _config(tmp_path)
    db_path = _database(tmp_path)
    before = db_path.stat().st_mtime_ns

    result = bridge.health(config_path=str(cfg))

    assert result["ready"] is True
    assert result["degraded"] is False
    assert result["canonical_first"] is True
    assert result["checks"]["database"]["status"] == "ok"
    assert result["checks"]["database"]["parity_sample"]["missing_by_layer"] == {
        "mempalace": 0,
        "honcho": 0,
        "neural_memory": 0,
    }
    assert db_path.stat().st_mtime_ns == before


def test_pending_sync_and_projection_drift_are_explicit_warnings(tmp_path: Path):
    cfg = _config(tmp_path)
    _database(tmp_path, pending=1, omit_layer="honcho")

    result = bridge.health(config_path=str(cfg))

    assert result["ready"] is True
    assert result["degraded"] is True
    assert set(result["warnings"]) == {
        "pending_canonical_sync",
        "layer_projection_drift",
    }
    assert result["checks"]["database"]["parity_sample"]["missing_by_layer"]["honcho"] == 1


def test_invalid_canonical_policy_blocks_readiness(tmp_path: Path):
    cfg = _config(tmp_path, canonical_first=False)
    _database(tmp_path)

    result = bridge.health(config_path=str(cfg))

    assert result["ok"] is True
    assert result["ready"] is False
    assert "canonical" in result["blocking"]


def test_api_and_bridge_share_the_same_contract(tmp_path: Path):
    cfg = _config(tmp_path)
    _database(tmp_path)

    api_result = TestClient(app).get("/health", params={"config_path": str(cfg)})

    assert api_result.status_code == 200
    api_payload = api_result.json()
    bridge_payload = bridge.health(config_path=str(cfg))

    # FD usage is live process telemetry and may change while TestClient opens
    # and closes worker resources. Compare the stable contract separately.
    api_fd = api_payload["checks"].pop("file_descriptors")
    bridge_fd = bridge_payload["checks"].pop("file_descriptors")
    assert api_payload == bridge_payload
    for fd_check in (api_fd, bridge_fd):
        assert fd_check["status"] in {"ok", "warning", "critical"}
        assert fd_check["used"] is None or fd_check["used"] >= 0
