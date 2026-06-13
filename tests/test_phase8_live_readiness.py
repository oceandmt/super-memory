from pathlib import Path

from fastapi.testclient import TestClient

from super_memory import bridge, mcp_server
from super_memory.api import app


def _config(tmp_path: Path) -> Path:
    cfg = tmp_path / "super-memory.yaml"
    cfg.write_text(f'workspace_root: "{tmp_path}"\nsqlite_path: data/test.sqlite3\n', encoding="utf-8")
    return cfg


def test_phase8_diagnostics_and_contracts(tmp_path: Path):
    cfg = _config(tmp_path)
    contract = bridge.memory_slot_contract(config_path=str(cfg))
    assert contract["ok"] is True
    assert contract["assertions"]["canonical_save_ok"] is True
    assert contract["assertions"]["graph_projection_ok"] is True

    diagnostics = bridge.diagnostics(config_path=str(cfg))
    assert diagnostics["ok"] is True
    assert diagnostics["checks"]["workspace_markdown_canonical"] is True
    assert diagnostics["checks"]["phase4_heavy_disabled_by_default"] is True

    mcp_contract = bridge.mcp_contract(config_path=str(cfg))
    assert mcp_contract["ok"] is True
    assert mcp_contract["tool_count"] >= 72

    smoke = bridge.supervised_runtime_smoke(config_path=str(cfg))
    assert smoke["ok"] is True


def test_phase8_dedup_train_import_watch(tmp_path: Path):
    cfg = _config(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "note.md").write_text("# Phase 8\n\nDecision: dedup should avoid duplicate chunk saves.", encoding="utf-8")
    first = bridge.train_local("docs", domain_tag="phase8", config_path=str(cfg))
    second = bridge.train_local("docs", domain_tag="phase8", config_path=str(cfg))
    assert first["saved_chunks"] == 1
    assert second["saved_chunks"] == 0
    assert second["skipped_chunks"] == 1

    (docs / "items.json").write_text('{"content":"import once", "tags":"single", "metadata":"bad"}', encoding="utf-8")
    imported1 = bridge.import_local("docs/items.json", config_path=str(cfg))
    imported2 = bridge.import_local("docs/items.json", config_path=str(cfg))
    assert imported1["saved_records"] == 1
    assert imported2["saved_records"] == 0
    assert imported2["skipped_records"] == 1

    scan1 = bridge.watch_scan("docs", save=True, config_path=str(cfg))
    scan2 = bridge.watch_scan("docs", save=True, config_path=str(cfg))
    assert scan1["ok"] is True
    assert scan2["changed"] == []


def test_phase8_reasoning_graph_api_mcp(tmp_path: Path):
    cfg = _config(tmp_path)
    hyp = bridge.hypothesis_create("Phase 8 keeps confidence history", config_path=str(cfg))
    ev = bridge.evidence_add(hyp["hypothesis_id"], "History entry is recorded", weight=0.6, config_path=str(cfg))
    detail = bridge.hypothesis_get(hyp["hypothesis_id"], config_path=str(cfg))
    assert detail["hypothesis"]["confidence_history"]
    assert detail["evidence"][0]["provenance"]["source"] == "super-memory.reasoning"

    expired = bridge.expire_predictions(config_path=str(cfg))
    assert expired["ok"] is True
    inc = bridge.graph_rebuild_incremental(config_path=str(cfg))
    cleanup = bridge.graph_cleanup_orphans(config_path=str(cfg))
    assert inc["ok"] is True
    assert cleanup["ok"] is True

    client = TestClient(app)
    assert client.post("/diagnostics", json={"config_path": str(cfg)}).json()["ok"] is True
    assert client.post("/memory-slot-contract", json={"config_path": str(cfg)}).json()["ok"] is True

    old = mcp_server.MCP_PROFILE
    mcp_server.MCP_PROFILE = "admin"
    try:
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        assert "super_memory_diagnostics" in names
        assert "super_memory_memory_slot_contract" in names
        call = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "super_memory_diagnostics", "arguments": {"config_path": str(cfg)}}})
        assert call["result"]["isError"] is False
    finally:
        mcp_server.MCP_PROFILE = old
