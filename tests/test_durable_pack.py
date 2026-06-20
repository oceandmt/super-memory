from pathlib import Path
import os

from fastapi.testclient import TestClient

from super_memory.api import app
from super_memory import bridge


def test_durable_pack_bridge_installs_and_qualifies(tmp_path: Path):
    old = os.environ.get("SUPER_MEMORY_WORKSPACE_ROOT")
    os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = str(tmp_path)
    try:
        result = bridge.durable_pack(qualify=True, debug=True)
        assert result["ok"] is True
        assert result["saved"]["ok"] is True
        assert len(result["saved"]["items"]) >= 6
        assert all(q["ok"] for q in result["qualification"])
        assert result["debug"]["health"]["ok"] is True
    finally:
        if old is None:
            os.environ.pop("SUPER_MEMORY_WORKSPACE_ROOT", None)
        else:
            os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = old


def test_durable_pack_api_endpoint(tmp_path: Path):
    old = os.environ.get("SUPER_MEMORY_WORKSPACE_ROOT")
    os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = str(tmp_path)
    client = TestClient(app)
    try:
        resp = client.post("/durable-pack", json={"qualify": True, "debug": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["pack_name"] == "openclaw-super-memory-durable-pack-v1"
        assert all(q["hit_count"] > 0 for q in body["qualification"])
    finally:
        if old is None:
            os.environ.pop("SUPER_MEMORY_WORKSPACE_ROOT", None)
        else:
            os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = old
