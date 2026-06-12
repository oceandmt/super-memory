from pathlib import Path

from super_memory import bridge, mcp_server


def _config(tmp_path: Path) -> Path:
    cfg = tmp_path / "super-memory.yaml"
    cfg.write_text(f'workspace_root: "{tmp_path}"\nsqlite_path: data/test.sqlite3\n', encoding="utf-8")
    return cfg


def test_phase1_batch_show_context_todo_auto_health(tmp_path: Path):
    cfg = _config(tmp_path)
    batch = bridge.remember_batch(
        [
            {"content": "Phase 1 batch decision keeps canonical markdown first.", "type": "decision", "scope": "shared", "project": "super-memory"},
            {"content": "Phase 1 workflow keeps derived layers synchronized.", "type": "workflow", "scope": "shared", "project": "super-memory"},
        ],
        config_path=str(cfg),
    )
    assert batch["ok"] is True
    assert len(batch["items"]) == 2

    memory_id = batch["items"][0]["record"]["id"]
    shown = bridge.show(memory_id, config_path=str(cfg))
    assert shown["ok"] is True
    assert {"mempalace", "honcho", "neural_memory"}.issubset(shown["layers"].keys())

    ctx = bridge.context("Phase 1", config_path=str(cfg))
    assert ctx["records"]

    todo = bridge.todo("Verify Phase 1 MCP tool exposure", priority=7, config_path=str(cfg))
    assert todo["record"]["type"] == "todo"

    auto = bridge.auto("decision: keep canonical markdown first\nnext: add health checks", save=True, config_path=str(cfg))
    assert len(auto["candidates"]) == 2
    assert auto["saved"]["ok"] is True

    health = bridge.health(config_path=str(cfg))
    assert health["ok"] is True
    assert health["canonical_first"] is True
    assert health["workspace_markdown_enabled"] is True


def test_phase1_mcp_tools_list_and_call(tmp_path: Path):
    old = mcp_server.MCP_PROFILE
    mcp_server.MCP_PROFILE = "normal"
    try:
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        for name in {
            "super_memory_remember_batch",
            "super_memory_show",
            "super_memory_context",
            "super_memory_todo",
            "super_memory_auto",
            "super_memory_stats",
            "super_memory_health",
        }:
            assert name in names

        cfg = _config(tmp_path)
        response = mcp_server.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "super_memory_health", "arguments": {"config_path": str(cfg)}},
            }
        )
        assert response["result"]["isError"] is False
        assert "canonical_first" in response["result"]["content"][0]["text"]
    finally:
        mcp_server.MCP_PROFILE = old
