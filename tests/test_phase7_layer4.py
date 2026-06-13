from pathlib import Path

from fastapi.testclient import TestClient

from super_memory import bridge, mcp_server
from super_memory.api import app


def _config(tmp_path: Path) -> Path:
    cfg = tmp_path / "super-memory.yaml"
    cfg.write_text(f'workspace_root: "{tmp_path}"\nsqlite_path: data/test.sqlite3\n', encoding="utf-8")
    return cfg


def test_phase7_graph_projection_and_recall(tmp_path: Path):
    cfg = _config(tmp_path)
    saved = bridge.remember({
        "content": "Decision: Layer 4 graph should project memories into neurons, synapses, and fibers",
        "type": "decision",
        "scope": "project",
        "project": "super-memory",
        "tags": ["layer4", "graph"],
        "trust_score": 0.9,
    }, config_path=str(cfg))
    assert saved["graph_projection"]["ok"] is True
    memory_id = saved["record"]["id"]

    stats = bridge.graph_stats(config_path=str(cfg))
    assert stats["fibers"] >= 1
    assert stats["neurons"].get("memory", 0) >= 1
    assert stats["synapses"]

    recall = bridge.graph_recall("Layer 4 graph", config_path=str(cfg))
    assert recall["fibers"]

    neighbors = bridge.graph_neighbors(memory_id, config_path=str(cfg))
    assert neighbors["neighbors"]


def test_phase7_cognitive_workflow(tmp_path: Path):
    cfg = _config(tmp_path)
    hyp = bridge.hypothesis_create("Layer 4 graph improves associative recall", confidence=0.55, tags=["layer4"], config_path=str(cfg))
    assert hyp["ok"] is True
    hyp_id = hyp["hypothesis_id"]

    ev = bridge.evidence_add(hyp_id, "Graph fibers can be recalled by query", direction="for", weight=0.7, config_path=str(cfg))
    assert ev["confidence"] > hyp["confidence"]

    pred = bridge.prediction_create("A graph recall query returns at least one fiber", hypothesis_id=hyp_id, config_path=str(cfg))
    assert pred["ok"] is True

    ver = bridge.verify_prediction(pred["prediction_id"], "correct", content="Test observed a returned fiber", config_path=str(cfg))
    assert ver["status"] == "confirmed"

    detail = bridge.hypothesis_get(hyp_id, config_path=str(cfg))
    assert len(detail["evidence"]) >= 2


def test_phase7_lifecycle_safe_flows_api_mcp(tmp_path: Path):
    cfg = _config(tmp_path)
    source = tmp_path / "docs"
    source.mkdir()
    (source / "note.md").write_text("# Note\n\nWorkflow: local train should save chunks safely.", encoding="utf-8")

    train = bridge.train_local("docs", domain_tag="test", config_path=str(cfg))
    assert train["ok"] is True
    assert train["saved_chunks"] == 1

    review = bridge.lifecycle_review(config_path=str(cfg))
    assert review["ok"] is True
    assert review["checked"] >= 1

    cache = bridge.lifecycle_cache("save", config_path=str(cfg))
    assert cache["ok"] is True

    scan = bridge.watch_scan("docs", config_path=str(cfg))
    assert scan["ok"] is True
    assert scan["daemon"] is False

    client = TestClient(app)
    response = client.get("/graph/stats", params={"config_path": str(cfg)})
    assert response.status_code == 200
    assert response.json()["fibers"] >= 1

    old = mcp_server.MCP_PROFILE
    mcp_server.MCP_PROFILE = "admin"
    try:
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        assert "super_memory_graph_stats" in names
        assert "super_memory_hypothesis_create" in names
        assert "super_memory_train_local" in names
        call = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "super_memory_graph_stats", "arguments": {"config_path": str(cfg)}}})
        assert call["result"]["isError"] is False
    finally:
        mcp_server.MCP_PROFILE = old
