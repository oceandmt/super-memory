from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import super_memory.mcp_server as mcp_server

EXPECTED_ADMIN_COUNT = 239
EXPECTED_USER_COUNT = 62
EXPECTED_READONLY_COUNT = 62
EXPECTED_P0_P5 = {
    "super_memory_post_turn_capture",
    "super_memory_session_start_context",
    "super_memory_session_end_summary",
    "super_memory_delegation_handoff",
    "super_memory_cross_scope_recall",
    "super_memory_extract_claims",
    "super_memory_find_contradictions",
    "super_memory_resolve_contradiction",
    "super_memory_agent_belief_report",
    "super_memory_create_session_summary",
    "super_memory_get_session_summary",
    "super_memory_list_session_summaries",
    "super_memory_search_session_archives",
    "super_memory_session_timeline_view",
    "super_memory_auto_handoff_on_spawn",
    "super_memory_load_current_handoff",
    "super_memory_complete_handoff_with_outcome",
    "super_memory_cross_agent_report",
    "super_memory_session_health",
    "super_memory_memory_pollution_report",
    "super_memory_export_memory_graph",
}


def tool_names(profile: str) -> set[str]:
    mcp_server.MCP_PROFILE = profile
    return {t["name"] for t in mcp_server._tool_descriptors()}


def test_tool_counts_by_profile():
    assert len(tool_names("admin")) == EXPECTED_ADMIN_COUNT
    assert len(tool_names("user")) == EXPECTED_USER_COUNT
    assert len(tool_names("readonly")) == EXPECTED_READONLY_COUNT


def test_admin_exposes_all_p0_p5_tools():
    names = tool_names("admin")
    assert EXPECTED_P0_P5 <= names


def test_user_profile_is_core_subset_of_admin():
    admin = tool_names("admin")
    user = tool_names("user")
    assert user <= admin
    assert "super_memory_remember" in user
    assert "super_memory_recall" in user
    assert "super_memory_status" in user


def test_tool_catalog_json_matches_runtime(tmp_path):
    root = Path(__file__).resolve().parents[1]
    res = subprocess.run(
        [sys.executable, "scripts/export_tool_catalog.py", "--format", "json"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    catalog = json.loads((root / "docs" / "TOOL_CATALOG.json").read_text())
    runtime_names = tool_names("admin")
    catalog_names = {t["name"] for t in catalog["tools"]}
    assert catalog["total_tools"] == EXPECTED_ADMIN_COUNT
    assert catalog_names == runtime_names


def test_tool_catalog_has_categories_and_profiles():
    root = Path(__file__).resolve().parents[1]
    catalog_path = root / "docs" / "TOOL_CATALOG.json"
    if not catalog_path.exists():
        subprocess.run(
            [sys.executable, "scripts/export_tool_catalog.py", "--format", "json"],
            cwd=root,
            check=True,
        )
    catalog = json.loads(catalog_path.read_text())
    for tool in catalog["tools"]:
        assert tool["category"]
        assert isinstance(tool["profiles"], list)
        assert "admin" in tool["profiles"]
