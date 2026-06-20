from pathlib import Path
import os

from fastapi.testclient import TestClient

from super_memory.api import app
from super_memory import bridge


def _with_workspace(tmp_path: Path):
    old = os.environ.get("SUPER_MEMORY_WORKSPACE_ROOT")
    os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = str(tmp_path)
    return old


def _restore_workspace(old: str | None):
    if old is None:
        os.environ.pop("SUPER_MEMORY_WORKSPACE_ROOT", None)
    else:
        os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = old


def test_durable_pack_bridge_installs_and_qualifies(tmp_path: Path):
    old = _with_workspace(tmp_path)
    try:
        result = bridge.durable_pack(qualify=True, debug=True)
        assert result["ok"] is True
        assert result["saved"]["ok"] is True
        assert len(result["saved"]["items"]) >= 6
        assert all(q["ok"] for q in result["qualification"])
        assert result["debug"]["health"]["ok"] is True
        assert result["status"]["duplicates_count"] == 0
    finally:
        _restore_workspace(old)


def test_durable_pack_idempotent_and_status(tmp_path: Path):
    old = _with_workspace(tmp_path)
    try:
        first = bridge.durable_pack(qualify=True, debug=False, dedupe=True)
        second = bridge.durable_pack(qualify=True, debug=False, dedupe=True)
        assert first["ok"] is True
        assert second["ok"] is True
        assert all(item.get("dedup", {}).get("skipped") for item in second["saved"]["items"])
        status = bridge.durable_pack_status()
        assert status["ok"] is True
        assert status["found_items"] == status["expected_items"]
        assert status["duplicates_count"] == 0
    finally:
        _restore_workspace(old)


def test_durable_pack_audit_fix_dedupes_manual_duplicate(tmp_path: Path):
    old = _with_workspace(tmp_path)
    try:
        bridge.durable_pack(qualify=True, debug=False, dedupe=True)
        # Simulate a pre-fix duplicate by bypassing remember_batch dedup with dedupe disabled and altered metadata only.
        dup = bridge.durable_pack(qualify=True, debug=False, dedupe=False)
        assert dup["ok"] is True
        audit = bridge.durable_pack_audit(fix=True)
        assert audit["after"]["duplicates_count"] == 0
    finally:
        _restore_workspace(old)


def test_durable_pack_api_endpoint(tmp_path: Path):
    old = _with_workspace(tmp_path)
    client = TestClient(app)
    try:
        resp = client.post("/durable-pack", json={"qualify": True, "debug": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["pack_name"] == "openclaw-super-memory-durable-pack-v1"
        assert all(q["hit_count"] > 0 for q in body["qualification"])

        status = client.post("/durable-pack/status", json={})
        assert status.status_code == 200
        assert status.json()["duplicates_count"] == 0

        audit = client.post("/durable-pack/audit", json={"fix": True})
        assert audit.status_code == 200
        assert "cross_layer_after" in audit.json()
    finally:
        _restore_workspace(old)
