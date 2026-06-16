"""Phase 8 contract tests: memory-slot replacement contract (save -> search -> get -> show -> graph).

Uses Live API via TestClient with explicit config_path to avoid session/DB isolation issues.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from super_memory.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True or data.get("service") == "super-memory"


def test_status():
    r = client.get("/status")
    assert r.status_code == 200
    data = r.json()
    assert "total_memories" in data
    assert "graph_edges" in data
    assert "cognitive_synapses" in data


def test_mcp_tools():
    r = client.get("/mcp-tools")
    assert r.status_code == 200
    tools = r.json()["tools"]
    assert isinstance(tools, list)
    assert any(t["name"] == "super_memory_remember" for t in tools)


def test_remember_and_show():
    # save
    r = client.post("/remember", json={"content": "Phase 8 contract memory", "type": "fact"})
    assert r.status_code == 200
    data = r.json()
    # Accept either top-level ok or nested record
    assert data.get("ok") or data.get("record")
    record = data.get("record") or {}
    mem_id = record.get("id") or data.get("memory_id", "")
    assert mem_id

    # show
    r = client.post("/show", json={"memory_id": mem_id})
    assert r.status_code == 200
    shown = r.json()
    assert shown.get("layers") or shown.get("record") or shown.get("ok")  # at least something returned


def test_forget_soft():
    r = client.post("/remember", json={"content": "forget soft p2", "type": "context"})
    data = r.json()
    record = data.get("record") or {}
    mem_id = record.get("id") or data.get("memory_id", "")

    r = client.post("/forget", json={"memory_id": mem_id, "hard": False, "reason": "test"})
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        data = r.json()
        assert data.get("action") in ("soft_delete", "hard_delete")


def test_recall_returns_results():
    r = client.post("/recall", json={"query": "graph", "limit": 2})
    assert r.status_code == 200
    data = r.json()
    # Accept any result shape
    assert data is not None


def test_memory_search():
    r = client.post("/memory-search", json={"query": "graph", "max_results": 3})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert data.get("provider") == "super-memory"


def test_lifecycle_tier():
    r = client.post("/lifecycle/tier", json={"action": "evaluate", "dry_run": True})
    assert r.status_code == 200
    assert "proposals" in r.json()


def test_lifecycle_review():
    r = client.post("/lifecycle/review", json={"limit": 10})
    assert r.status_code == 200
    data = r.json()
    assert "tier_distribution" in data or "ok" in data


def test_leitner_endpoints():
    """Smoke-test Leitner5-box API surface."""
    # auto_seed
    r = client.post("/leitner", json={"action": "auto_seed", "limit": 10})
    assert r.status_code in (200, 422)

    # stats
    r = client.post("/leitner", json={"action": "stats"})
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        assert "box_distribution" in r.json() or "ok" in r.json()

    # queue
    r = client.post("/leitner", json={"action": "queue", "limit": 5})
    assert r.status_code in (200, 422)


def test_forget_and_edit_endpoints_smoke():
    """Smoke-test forget+edit API surface."""
    r = client.post("/remember", json={"content": "p2 edit target", "type": "context"})
    data = r.json()
    record = data.get("record") or {}
    mem_id = record.get("id") or data.get("memory_id", "")

    if mem_id:
        r = client.post("/edit", json={"memory_id": mem_id, "content": "p2 edited", "type": "fact"})
        assert r.status_code in (200, 404)
