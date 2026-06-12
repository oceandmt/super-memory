from pathlib import Path

from fastapi.testclient import TestClient

from super_memory.api import app


def test_api_remember_status_prefetch_promote(tmp_path: Path):
    client = TestClient(app)
    config_payload = {"config_path": None}

    # Use env override to keep API test isolated.
    import os
    old = os.environ.get("SUPER_MEMORY_WORKSPACE_ROOT")
    os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = str(tmp_path)
    try:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True

        remember = client.post(
            "/remember",
            json={
                "content": "API promotion decision for super-memory.",
                "type": "decision",
                "scope": "shared",
                "agent_id": "lucas",
                "project": "super-memory",
                "tags": ["api-test"],
            },
        )
        assert remember.status_code == 200
        body = remember.json()
        memory_id = body["record"]["id"]
        assert len(body["results"]) == 4

        status = client.get("/status")
        assert status.status_code == 200
        # SQLite status covers the three derived layers; canonical Markdown is file-backed.
        assert status.json()["total_memories"] == 3

        prefetch = client.post("/prefetch", json={"query": "promotion", "limit": 5})
        assert prefetch.status_code == 200
        assert prefetch.json()["records"]

        promoted = client.post("/promote", json={"memory_id": memory_id})
        assert promoted.status_code == 200
        assert promoted.json()["ok"] is True
        assert (tmp_path / "MEMORY.md").exists()
    finally:
        if old is None:
            os.environ.pop("SUPER_MEMORY_WORKSPACE_ROOT", None)
        else:
            os.environ["SUPER_MEMORY_WORKSPACE_ROOT"] = old
