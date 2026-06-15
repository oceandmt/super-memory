import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from super_memory import bridge, mcp_server
from super_memory.api import app


def _config(tmp_path: Path) -> Path:
    cfg = tmp_path / "super-memory.yaml"
    cfg.write_text(f'workspace_root: "{tmp_path}"\nsqlite_path: data/test.sqlite3\n', encoding="utf-8")
    return cfg


def test_phase2_contract_memory_search_get_and_dynamic_tools(tmp_path: Path):
    cfg = _config(tmp_path)
    saved = bridge.remember({"content": "slot behavior contract memory", "type": "fact", "scope": "shared"}, config_path=str(cfg))
    assert saved["results"][0]["layer"] == "workspace_markdown"

    searched = bridge.memory_search("slot behavior", config_path=str(cfg))
    assert searched["provider"] == "super-memory"
    assert searched["results"]

    got = bridge.memory_get(searched["results"][0]["path"], config_path=str(cfg))
    assert "slot behavior" in got["content"]

    client = TestClient(app)
    tools = client.get("/mcp-tools").json()["tools"]
    names = {tool["name"] for tool in tools}
    assert "super_memory_memory_search" in names
    assert "super_memory_memory_get" in names


def test_phase2_plugin_client_and_index_are_syntax_valid():
    subprocess.run(["node", "--check", "openclaw-plugin/super-memory/index.js"], check=True)
    subprocess.run(["node", "--check", "openclaw-plugin/super-memory/mcp-client.js"], check=True)


def test_phase3_advanced_memory_intelligence_surface(tmp_path: Path):
    cfg = _config(tmp_path)
    rec = bridge.remember({"content": "Phase 3 provenance memory", "type": "fact", "scope": "shared"}, config_path=str(cfg))["record"]
    memory_id = rec["id"]

    assert bridge.conflicts(content="Phase 3 provenance memory", config_path=str(cfg))["ok"] is True
    assert bridge.provenance(memory_id, config_path=str(cfg))["ok"] is True
    assert bridge.source({"name": "unit-test-source", "source_type": "document"}, config_path=str(cfg))["ok"] is True
    assert bridge.version(name="unit-snapshot", config_path=str(cfg))["ok"] is True
    assert bridge.pin(memory_id, config_path=str(cfg))["ok"] is True
    assert bridge.consolidate(config_path=str(cfg))["ok"] is True
    assert bridge.gaps("missing advanced recall", config_path=str(cfg))["ok"] is True
    assert bridge.explain("Phase 3", "provenance", config_path=str(cfg))["ok"] is True
    assert bridge.situation(config_path=str(cfg))["ok"] is True
    assert bridge.reflex(memory_id, config_path=str(cfg))["ok"] is True
    assert bridge.boundaries(domain="memory", content="Canonical markdown stays first", config_path=str(cfg))["ok"] is True


def test_phase3_mcp_admin_exposes_advanced_tools(tmp_path: Path):
    old = mcp_server.MCP_PROFILE
    mcp_server.MCP_PROFILE = "admin"
    try:
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        for name in ["super_memory_conflicts", "super_memory_provenance", "super_memory_source", "super_memory_version", "super_memory_boundaries"]:
            assert name in names

        response = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "super_memory_version", "arguments": {"name": "mcp-snapshot", "config_path": str(_config(tmp_path))}}})
        assert response["result"]["isError"] is False
    finally:
        mcp_server.MCP_PROFILE = old


def test_phase4_optional_heavy_features_are_safe_stubs():
    # Phase 7 implemented real workspace-only flows for train/index
    # These should return ok=True when dependencies are available
    for action in ["train", "index"]:
        result = bridge.optional_heavy(action, target="demo")
        # Should succeed (workspace-only) but may fail if dependencies missing
        # In test environment, basic deps should be present
        assert result["ok"] is True, f"{action} should succeed in test env"
        assert result["enabled"] is True
    # Remaining actions remain stubs
    for action in ["sync", "telegram_backup", "visualize", "store", "watch"]:
        result = bridge.optional_heavy(action, target="demo")
        assert result["ok"] is False
        assert result["enabled"] is False
