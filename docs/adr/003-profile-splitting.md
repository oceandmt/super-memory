# ADR 003: MCP Profile Splitting Strategy

Date: 2026-06-17

Status: Accepted

## Context

The MCP server exposes 133 tools when running with an `admin` profile,
but only 17 tools for `normal` users. We need a clear, maintainable
strategy for which tools are exposed at each profile level.

## Decision

We define **three MCP profiles** with nested tool sets:

```
  NORMAL_TOOLS (17)
    ↓ includes
  ADMIN_TOOLS = NORMAL_TOOLS + 14 = 31
    ↓ includes
  ALL_TOOLS = set(TOOLS) = 133
```

### Profile Definitions

| Profile  | Tools | Access Pattern |
|----------|-------|----------------|
| `normal` (default) | 17 core read/write/health tools | Safe for any agent in any channel |
| `admin`  | 31 tools including promote, conflicts, provenance | Trusted agents only |
| `all`    | All 133 tools (full register) | Development, diagnostics, and CI |

### Tool Registration Sources

Tools are registered from 12 submodules:

- `mempalace/tools.py` → `MEMPALACE_TOOLS`
- `honcho/tools.py` → `HONCHO_TOOLS`
- `cross_agent.py` → `CROSS_AGENT_TOOLS`
- `session_timeline.py` → `SESSION_TIMELINE_TOOLS`
- `capture_hook.py` → `CAPTURE_HOOK_TOOLS`
- `handoff.py` → `HANDOFF_TOOLS`
- `synthesis.py` → `SYNTHESIS_TOOLS`
- `hooks.py` → `HOOKS_TOOLS`
- `hybrid_recall.py` → `HYBRID_RECALL_TOOLS`
- `claim_extractor.py` → `CLAIM_EXTRACTOR_TOOLS`
- `session_archive.py` → `SESSION_ARCHIVE_TOOLS`
- `reports.py` → `REPORTS_TOOLS`

Plus 40 inline-defined tools for infrastructure operations (train,
import, index, watch, etc.) that are only exposed in the `admin` profile.

### Caching

To avoid rebuilding the tool descriptor list on every MCP request,
`_allowed_tools()` and `_tool_descriptors()` use module-level caches
keyed by profile name. The cache is populated on first access and never
invalidated (tools are compiled once at import time).

## Consequences

- **Positive**: Clear security boundary — normal agents cannot invoke
  admin tools even if they know the tool name.
- **Positive**: Snapshot tests (`test_tool_catalog_snapshot.py`)
  enforce that tool counts remain stable across code changes.
- **Negative**: Adding a new tool requires updating the corresponding
  `*_TOOLS` list AND potentially the `NORMAL_TOOLS`, `ADMIN_TOOLS`, or
  `ADVANCED_TOOLS` sets. The test will catch mismatches.

## See Also

- `super_memory/mcp_server.py` — Profile definitions and cache
- `tests/test_tool_catalog_snapshot.py` — Snapshot enforcement
- `tests/test_mcp_server.py` — Profile access control tests
