from pathlib import Path

from fastapi.testclient import TestClient

from super_memory import bridge, mcp_server
from super_memory.api import app


def _config(tmp_path: Path) -> Path:
    cfg = tmp_path / "super-memory.yaml"
    cfg.write_text(f'workspace_root: "{tmp_path}"\nsqlite_path: data/test.sqlite3\n', encoding="utf-8")
    return cfg


def test_phase6_working_memory_attention_and_parallel_save(tmp_path: Path):
    cfg = _config(tmp_path)
    set_result = bridge.working_memory_set({"current_task": "implement phase 6"}, config_path=str(cfg))
    assert set_result["ok"] is True
    assert bridge.working_memory_get(config_path=str(cfg))["memory"]["current_task"] == "implement phase 6"

    payload = {
        "content": "Decision: Phase 6 workflow should use canonical markdown first for cognitive orchestration",
        "project": "super-memory",
        "tags": ["workflow"],
        "trust_score": 0.9,
    }
    scored = bridge.attention_score(payload, config_path=str(cfg))
    assert scored["salience"] in {"high", "critical"}
    assert "workspace_markdown" in scored["routes"]
    assert scored["promotion_candidate"] is True

    saved = bridge.parallel_save(payload, config_path=str(cfg))
    assert saved["ok"] is True
    assert saved["saved"] is True
    assert saved["save_result"]["results"][0]["layer"] == "workspace_markdown"


def test_phase6_recall_arbitration_consolidation_and_feedback(tmp_path: Path):
    cfg = _config(tmp_path)
    saved = bridge.parallel_save({
        "content": "Workflow: repeated blocker fixes should become promotion candidates",
        "project": "super-memory",
        "tags": ["workflow"],
    }, config_path=str(cfg))
    memory_id = saved["save_result"]["record"]["id"]

    arb = bridge.recall_arbitrate("workflow blocker", config_path=str(cfg))
    assert arb["answer_context"]
    assert arb["winner_policy"] in {"workspace_markdown", "mempalace", "honcho", "neural_memory"}

    consolidation = bridge.consolidation_cycle(config_path=str(cfg))
    assert consolidation["ok"] is True
    assert consolidation["checked"] >= 1

    candidates = bridge.promotion_candidates(config_path=str(cfg))
    assert candidates["ok"] is True
    assert candidates["candidates"]

    feedback = bridge.feedback_outcome(memory_id=memory_id, success=True, outcome="workflow succeeded", config_path=str(cfg))
    assert feedback["ok"] is True

    resolved = bridge.conflict_resolve("conflict:test", "keep_canonical", reason="markdown is source", config_path=str(cfg))
    assert resolved["ok"] is True


def test_phase6_api_and_mcp_admin_surface(tmp_path: Path):
    cfg = _config(tmp_path)
    client = TestClient(app)
    response = client.post("/attention-score", json={"payload": {"content": "Decision: remember this workflow", "project": "super-memory"}, "config_path": str(cfg)})
    assert response.status_code == 200
    assert response.json()["attention_score"] > 0

    response = client.post("/parallel-save", json={"payload": {"content": "Workflow: API phase6 save", "project": "super-memory"}, "config_path": str(cfg)})
    assert response.status_code == 200
    assert response.json()["ok"] is True

    old = mcp_server.MCP_PROFILE
    mcp_server.MCP_PROFILE = "admin"
    try:
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        for name in ["super_memory_working_memory_get", "super_memory_attention_score", "super_memory_parallel_save", "super_memory_recall_arbitrate"]:
            assert name in names

        call = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "super_memory_attention_score", "arguments": {"payload": {"content": "Decision: MCP phase6 workflow"}, "config_path": str(cfg)}}})
        assert call["result"]["isError"] is False
    finally:
        mcp_server.MCP_PROFILE = old
