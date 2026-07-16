"""Admin tool dispatch smoke: every tool descriptor must dispatch without hard error.

Uses minimal/empty mock args for tools that accept empty/dummy input.
Tools that require a valid memory_id or specific parameter are accepted
with a controlled ValueError (required arg missing) rather than crash.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from super_memory import mcp_server

# All admin-level tool names that should dispatch without hard error
TOOL_NAMES = sorted(mcp_server._allowed_tools("admin"))

SKIP_HARD = {
    # These need a path on disk and throw OSError — fine to skip
    "super_memory_train_local",
    "super_memory_index_local",
    "super_memory_import_local",
    "super_memory_watch_scan",
    "super_memory_train",
    "super_memory_index",
    "super_memory_import",
    # Only works with actual openclaw gateway — skip
    "super_memory_export_memory_graph",
    # Explicit maintenance operations are intentionally destructive or
    # corpus-sized. Dispatching them with empty args must not run against the
    # live default database in a no-hard-crash smoke test. They have dedicated
    # focused tests using disposable configs.
    "super_memory_reindex_all",
    "super_memory_reindex_fts_only",
    "super_memory_graph_rebuild",
    "super_memory_autocomplete_rebuild",
    "super_memory_index_sessions",
}


def _call_tool(name: str) -> dict[str, Any]:
    """Attempt a call; return {ok, error/warning, tool_name}."""
    try:
        mcp_server._call_tool(name, {})
        return {"ok": True, "tool_name": name}
    except (TypeError, ValueError, KeyError) as exc:
        # These are expected for tools that require args — not a crash
        return {"ok": True, "tool_name": name, "warning": f"{type(exc).__name__}: {exc}"}
    except PermissionError:
        return {"ok": True, "tool_name": name, "warning": "profile_restricted"}
    except Exception as exc:
        return {"ok": False, "tool_name": name, "error": f"{type(exc).__name__}: {exc}"}


@pytest.mark.parametrize("tool_name", TOOL_NAMES)
def test_tool_dispatch_no_hard_crash(tool_name: str):
    if tool_name in SKIP_HARD:
        pytest.skip("requires disk/gateway resource")
    result = _call_tool(tool_name)
    assert result["ok"], f"{tool_name} hard-failed: {result.get('error')}"
