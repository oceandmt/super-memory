from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from super_memory.claim_extractor import ClaimExtractor
from super_memory.db import validate_agent_scope, validate_session_scope, validate_status
from super_memory.handoff import HandoffTools
from super_memory.hooks import HookManager
from super_memory.migrations import run_migrations
from super_memory.models import SuperMemoryConfig
from super_memory.session_archive import SessionArchive


@pytest.fixture()
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SuperMemoryConfig:
    monkeypatch.setenv("SUPER_MEMORY_WORKSPACE_ROOT", str(tmp_path))
    return SuperMemoryConfig(workspace_root=tmp_path, sqlite_path="data/edge.sqlite3")


def table_columns(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {r[1] for r in conn.execute("PRAGMA table_info(" + table + ")")}


def test_migration_idempotent(cfg):
    first = run_migrations(cfg)
    second = run_migrations(cfg)
    third = run_migrations(cfg)
    assert first["ok"] and second["ok"] and third["ok"]
    assert second["change_count"] == 0
    assert third["change_count"] == 0


def test_dirty_memories_table_gets_missing_columns(cfg):
    db_path = Path(cfg.workspace_root) / cfg.sqlite_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, content TEXT NOT NULL)")
        conn.execute("INSERT INTO memories(id,content) VALUES('m1','legacy')")
    run_migrations(cfg)
    cols = table_columns(db_path, "memories")
    assert {"layer", "type", "scope", "agent_id", "created_at", "metadata_json"} <= cols


def test_dirty_honcho_events_table_gets_missing_columns(cfg):
    db_path = Path(cfg.workspace_root) / cfg.sqlite_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE honcho_events (id TEXT PRIMARY KEY, content TEXT)")
        conn.execute("INSERT INTO honcho_events(id,content) VALUES('e1','legacy')")
    run_migrations(cfg)
    cols = table_columns(db_path, "honcho_events")
    assert {"memory_id", "workspace", "session_id", "observer_peer_id", "created_at"} <= cols


@pytest.mark.parametrize("value", ["agent:lucas'; DROP TABLE memories; --", "agent:lucas) OR 1=1 --", "agent:\"bad"])
def test_agent_scope_injection_rejected(value):
    with pytest.raises(ValueError):
        validate_agent_scope(value)


@pytest.mark.parametrize("value", ["session:s1'; DROP TABLE sessions; --", "session:s1) OR 1=1 --", "session:\"bad"])
def test_session_scope_injection_rejected(value):
    with pytest.raises(ValueError):
        validate_session_scope(value)


@pytest.mark.parametrize("value", ["completed; DROP TABLE handoff_bundles", "bad", "claimed OR 1=1"])
def test_status_injection_rejected(value):
    with pytest.raises(ValueError):
        validate_status(value)


def test_empty_content_claim_extraction(cfg):
    ext = ClaimExtractor(cfg)
    assert ext._extract("", "lucas", "m1") == []


def test_unicode_vietnamese_claim_extraction_safe(cfg):
    ext = ClaimExtractor(cfg)
    claims = ext._extract("Lucas prefers ghi nhớ markdown. Quyết định: dùng schema.sql.", "lucas", "m1")
    assert isinstance(claims, list)


def test_json_looking_content_claim_extraction_safe(cfg):
    ext = ClaimExtractor(cfg)
    claims = ext._extract('{"Lucas":"prefers markdown"}', "lucas", "m1")
    assert isinstance(claims, list)


def test_large_content_claim_extraction_capped(cfg):
    ext = ClaimExtractor(cfg)
    text = " ".join(["Lucas prefers markdown memory."] * 100)
    claims = ext._extract(text, "lucas", "m1")
    assert len(claims) <= 20


def test_handoff_status_does_not_accept_bad_values(cfg):
    handoff = HandoffTools(cfg)
    with pytest.raises(ValueError):
        handoff.update_handoff_status("missing", "done;drop")


def test_handoff_create_and_complete_transaction(cfg):
    handoff = HandoffTools(cfg)
    created = handoff.create_handoff("lucas", "alex", "Title", "Summary", "s1", "memory", 2, {"x": 1})
    assert created["ok"] is True
    completed = handoff.complete_handoff_with_outcome(created["bundle_id"], "done", [], "passed")
    assert completed["ok"] is True


def test_concurrent_post_turn_capture_smoke(cfg):
    manager = HookManager(cfg)
    def work(i: int):
        return manager.post_turn_capture(f"user {i}", f"assistant {i}", "s-concurrent", "lucas", "openclaw")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(work, range(8)))
    assert all(r["ok"] for r in results)
    with manager._conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM honcho_events WHERE session_id='s-concurrent'").fetchone()[0]
    assert count >= 8


def test_concurrent_handoff_create_smoke(cfg):
    handoff = HandoffTools(cfg)
    def work(i: int):
        return handoff.create_handoff("lucas", "alex", f"Title {i}", "Summary", f"s{i}", "memory", 1, {})
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(work, range(8)))
    assert all(r["ok"] for r in results)


def test_sql_safety_script_passes():
    import subprocess, sys
    root = Path(__file__).resolve().parents[1]
    res = subprocess.run([sys.executable, "scripts/check_sql_safety.py"], cwd=root, text=True, capture_output=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "SQL_SAFETY_OK" in res.stdout


def test_tool_contract_script_passes():
    import subprocess, sys
    root = Path(__file__).resolve().parents[1]
    res = subprocess.run([sys.executable, "scripts/check_tool_contracts.py"], cwd=root, text=True, capture_output=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "TOOL_CONTRACTS_OK" in res.stdout


def test_contract_p0_p5_tool_count():
    from super_memory import mcp_server
    mcp_server.MCP_PROFILE = "admin"
    tools = {t["name"] for t in mcp_server._tool_descriptors()}
    expected = {
        "super_memory_post_turn_capture", "super_memory_session_start_context",
        "super_memory_session_end_summary", "super_memory_delegation_handoff",
        "super_memory_cross_scope_recall", "super_memory_extract_claims",
        "super_memory_find_contradictions", "super_memory_resolve_contradiction",
        "super_memory_agent_belief_report", "super_memory_create_session_summary",
        "super_memory_get_session_summary", "super_memory_list_session_summaries",
        "super_memory_search_session_archives", "super_memory_session_timeline_view",
        "super_memory_auto_handoff_on_spawn", "super_memory_load_current_handoff",
        "super_memory_complete_handoff_with_outcome", "super_memory_cross_agent_report",
        "super_memory_session_health", "super_memory_memory_pollution_report",
        "super_memory_export_memory_graph",
    }
    assert expected <= tools


def test_preflight_script_exists_and_executable_shape():
    path = Path(__file__).resolve().parents[1] / "scripts" / "super_memory_preflight.sh"
    text = path.read_text()
    assert "check_sql_safety.py" in text
    assert "check_tool_contracts.py" in text
    assert "SUPER_MEMORY_PREFLIGHT_OK" in text
