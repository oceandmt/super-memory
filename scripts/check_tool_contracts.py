#!/usr/bin/env python3
"""Tool contract drift checker for super-memory MCP server.

Verifies that tool descriptors match dispatch routing and manifest contracts.

Exit 0 if all contracts valid, exit 1 if drift detected.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load_manifest() -> dict:
    """Load openclaw.plugin.json manifest."""
    root = Path(__file__).parent.parent
    candidates = [
        root / "openclaw-plugin" / "super-memory" / "openclaw.plugin.json",
        root / "openclaw.plugin.json",
    ]
    for manifest_path in candidates:
        if manifest_path.exists():
            return json.loads(manifest_path.read_text())
    print(f"ERROR: manifest not found in: {candidates}", file=sys.stderr)
    sys.exit(1)


def get_mcp_tools() -> list[dict]:
    """Load tool descriptors from mcp_server."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from super_memory import mcp_server
    mcp_server.MCP_PROFILE = "admin"
    return mcp_server._tool_descriptors()


def main() -> int:
    manifest = load_manifest()
    manifest_tools = {t["name"]: t for t in manifest.get("tools", [])}
    if not manifest_tools:
        manifest_tools = {t: t for t in manifest.get("contracts", {}).get("tools", [])}
    
    mcp_tools = get_mcp_tools()
    mcp_tool_names = {t["name"] for t in mcp_tools}
    
    # Check 1: manifest tools exist in MCP (skip known optional/compatibility tools)
    known_optional = {
        "memory_get", "memory_search",  # legacy memory shims
        "super_memory_get_compatible", "super_memory_search_compatible",  # compat wrappers
        "super_memory_mcp_tools_list",  # dynamic proxy
    }
    orphan_contracts = []
    for name in manifest_tools:
        if name not in mcp_tool_names and name not in known_optional:
            orphan_contracts.append(name)
    
    # Check 2: P0-P5 tools are in manifest
    p0_p5_tools = [
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
    ]
    
    missing_contracts = []
    for tool in p0_p5_tools:
        if tool not in manifest_tools:
            missing_contracts.append(tool)
    
    if orphan_contracts or missing_contracts:
        print("TOOL_CONTRACTS_DRIFT")
        if orphan_contracts:
            print(f"Orphan contracts (in manifest but not in MCP): {len(orphan_contracts)}")
            for name in orphan_contracts[:10]:
                print(f"  {name}")
        if missing_contracts:
            print(f"Missing P0-P5 contracts (in MCP but not in manifest): {len(missing_contracts)}")
            for name in missing_contracts[:10]:
                print(f"  {name}")
        return 1
    
    print("TOOL_CONTRACTS_OK")
    print(f"Verified {len(manifest_tools)} manifest contracts, {len(mcp_tools)} MCP tools, 21 P0-P5 tools.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
