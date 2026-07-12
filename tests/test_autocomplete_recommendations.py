from pathlib import Path

from super_memory import mcp_server
from super_memory.models import MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from super_memory.service import SuperMemoryService
from super_memory import bridge


def _config(tmp_path: Path) -> str:
    path = tmp_path / "super-memory.yaml"
    path.write_text(f'workspace_root: "{tmp_path}"\nsqlite_path: data/test.sqlite3\n', encoding="utf-8")
    return str(path)


def test_autocomplete_rebuild_and_suggest(tmp_path: Path):
    cfg = SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/test.sqlite3")
    config_path = _config(tmp_path)
    svc = SuperMemoryService(cfg)
    assert all(r.ok for r in svc.save(MemoryRecord(
        id="ac-1",
        content="Recommendation autocomplete should help operators find memory actions quickly.",
        type=MemoryType.CONTEXT,
        scope=MemoryScope.PROJECT,
        project="super-memory",
    )))
    assert all(r.ok for r in svc.save(MemoryRecord(id="ac-2", content="Autocomplete prefix suggestions are deterministic.", type=MemoryType.CONTEXT)))
    rebuilt = bridge.autocomplete_rebuild(config_path=config_path)
    assert rebuilt["ok"]
    assert rebuilt["entries_inserted"] > 0

    suggested = bridge.autocomplete_suggest("auto", limit=5, config_path=config_path)
    assert suggested["ok"]
    assert any("Autocomplete" in item["text"] for item in suggested["suggestions"])


def test_recommendations_and_mcp_tool_exposed(tmp_path: Path):
    config_path = _config(tmp_path)
    result = bridge.recommendations(limit=5, config_path=config_path)
    assert result["ok"]
    assert result["recommendations"]
    assert {"action", "reason", "priority"} <= set(result["recommendations"][0])

    old = mcp_server.MCP_PROFILE
    try:
        mcp_server.MCP_PROFILE = "admin"
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        assert "super_memory_recommendations" in names

        called = mcp_server.handle({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "super_memory_recommendations", "arguments": {"limit": 3, "config_path": config_path}},
        })
        assert called["result"]["isError"] is False
    finally:
        mcp_server.MCP_PROFILE = old
