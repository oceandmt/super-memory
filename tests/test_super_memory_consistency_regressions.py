from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from super_memory import bridge, mcp_server
from super_memory.capture_hook import CaptureHook
from super_memory.config import load_config
from super_memory.cross_agent import CrossAgentTools
from super_memory.hybrid_recall import HybridRecall
from super_memory.migrations import run_migrations
from super_memory.models import MemoryRecord, MemoryScope, MemoryType, SuperMemoryConfig
from super_memory.service import SuperMemoryService
from super_memory.session_archive import SessionArchive


def _cfg(tmp_path: Path) -> SuperMemoryConfig:
    return SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/test.sqlite3")


def test_capture_turn_standalone_not_orphan_projection(tmp_path: Path):
    cfg = _cfg(tmp_path)
    run_migrations(cfg)
    CaptureHook(cfg).capture_turn("User wants standalone Honcho capture", session_id="s-capture")
    health = bridge.cross_layer_health(config_path=None) if False else None
    # Call bridge with an explicit config file so the audit uses this temp DB.
    config_file = tmp_path / "super-memory.yaml"
    config_file.write_text(f'workspace_root: "{tmp_path}"\nsqlite_path: data/test.sqlite3\n', encoding="utf-8")
    health = bridge.cross_layer_health(config_path=str(config_file))
    assert health["ok"], health
    assert health["orphan_projections_total"] == 0


def test_hybrid_markdown_recall_filters_workspace_layer(tmp_path: Path):
    cfg = _cfg(tmp_path)
    run_migrations(cfg)
    svc = SuperMemoryService(cfg)
    rec = MemoryRecord(content="markdown-only layer filter regression", agent_id="lucas", session_id="s1")
    svc.save(rec)
    recall = HybridRecall(cfg)
    res = recall.cross_scope_recall("layer filter", agent_scope="agent:lucas", session_scope="session:s1", source_layers=["markdown"], limit=10)
    assert res["results"]
    assert all(r["provenance"]["layer"] == "markdown" for r in res["results"])


def test_cross_agent_recall_prefers_canonical_row(tmp_path: Path):
    cfg = _cfg(tmp_path)
    run_migrations(cfg)
    svc = SuperMemoryService(cfg)
    rec = MemoryRecord(content="cross agent dedup canonical regression", agent_id="lucas", scope=MemoryScope.SHARED)
    svc.save(rec)
    res = CrossAgentTools(cfg).cross_agent_recall("dedup canonical", "lucas", limit=10)
    ids = [m["id"] for m in res["memories"]]
    assert ids == [rec.id]
    assert res["memories"][0]["layer"] == "workspace_markdown"


def test_session_archive_dedups_memory_projection(tmp_path: Path):
    cfg = _cfg(tmp_path)
    run_migrations(cfg)
    svc = SuperMemoryService(cfg)
    rec = MemoryRecord(content="decision: archive dedup regression", agent_id="lucas", session_id="s-archive", type=MemoryType.DECISION)
    svc.save(rec)
    result = SessionArchive(cfg).create_session_summary("s-archive")
    assert result["event_count"] == 1, result


def test_flush_pending_restores_workspace_sqlite_mirror(tmp_path: Path):
    cfg = _cfg(tmp_path)
    run_migrations(cfg)
    svc = SuperMemoryService(cfg)
    import hashlib
    rec = MemoryRecord(content="pending sync mirror regression", agent_id="lucas")
    rec.metadata["content_hash"] = hashlib.sha256(rec.content.encode("utf-8", errors="replace")).hexdigest()
    # Simulate fallback-derived layers without a workspace_markdown SQLite row.
    from super_memory.layers import SQLiteLayerBackend
    from super_memory.models import MemoryLayer
    for layer in [MemoryLayer.MEMPALACE, MemoryLayer.HONCHO, MemoryLayer.NEURAL_MEMORY]:
        clone = rec.model_copy(deep=True)
        clone.metadata["pending_canonical_sync"] = True
        SQLiteLayerBackend(cfg, layer).save(clone)
    flushed = svc.flush_pending()
    assert rec.id in flushed
    db_path = Path(cfg.workspace_root) / cfg.sqlite_path
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM memories WHERE id=? AND layer='workspace_markdown'", (rec.id,)).fetchone()[0]
    assert count == 1


def test_mcp_exposes_cross_layer_health(tmp_path: Path):
    cfg_file = tmp_path / "super-memory.yaml"
    cfg_file.write_text(f'workspace_root: "{tmp_path}"\nsqlite_path: data/test.sqlite3\n', encoding="utf-8")
    old = mcp_server.MCP_PROFILE
    try:
        mcp_server.MCP_PROFILE = "admin"
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {t["name"] for t in tools["result"]["tools"]}
        assert "super_memory_cross_layer_health" in names
        resp = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "super_memory_cross_layer_health", "arguments": {"config_path": str(cfg_file)}}})
        payload = json.loads(resp["result"]["content"][0]["text"])
        assert "ok" in payload
    finally:
        mcp_server.MCP_PROFILE = old


def test_api_token_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("SUPER_MEMORY_API_TOKEN", "secret-token")
    cfg = load_config()
    assert cfg.api_token == "secret-token"
