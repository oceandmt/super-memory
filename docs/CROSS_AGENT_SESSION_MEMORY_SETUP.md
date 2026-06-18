# Cross-Agent & Cross-Session Memory Setup

This guide explains how to install, configure, and operate Super Memory's cross-agent and cross-session memory features.

## Status

Super Memory already includes cross-agent and cross-session memory primitives:

- agent-scoped memories through `agent_id` and `agent:<id>` tags
- session-scoped memories through `session_id`
- shared/project/cross-agent scopes through `scope`
- Honcho-style session events and peer context in `honcho_events`
- cross-agent recall/comparison tools
- session timeline/archive/search tools
- handoff bundles for delegation
- hybrid cross-scope recall across markdown/Honcho/MemPalace/graph
- reports for cross-agent/session health and pollution

The canonical source of truth remains Workspace Markdown. SQLite rows are derived mirrors/projections used for fast cross-agent/session operations.

## 1. Install

```bash
git clone <repo-url> super-memory
cd super-memory
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest tests/test_mcp_server.py tests/test_multi_agent_graph.py tests/test_phase8_contracts.py -q
```

## 2. Configure workspace and database

The minimum setup is a workspace root and a SQLite path.

Quick wizard:

```bash
super-memory setup \
  --workspace-root /home/oceandmt/.openclaw/workspace \
  --output super-memory.yaml \
  --overwrite
```

Environment variables:

```bash
export SUPER_MEMORY_WORKSPACE_ROOT=/home/oceandmt/.openclaw/workspace
export SUPER_MEMORY_SQLITE_PATH=data/super-memory.sqlite3
```

Or create `super-memory.yaml` in the project/current working directory:

```yaml
workspace_root: /home/oceandmt/.openclaw/workspace
sqlite_path: data/super-memory.sqlite3
daily_memory_dir: memory
long_term_file: MEMORY.md
registers_dir: memory/registers
require_canonical_first: true
enabled_layers:
  - workspace_markdown
  - mempalace
  - honcho
  - neural_memory
```

Important rules:

- `workspace_markdown` must stay enabled for canonical-first behavior.
- `require_canonical_first: true` is recommended.
- Do not put secrets in memory content, tags, or metadata.
- Use stable `agent_id` values such as `lucas`, `alex`, `max`, `isol`.
- Use stable `session_id` values from the runtime/chat/session whenever available.

## 3. Run the MCP server

For daily-safe tools:

```bash
super-memory-mcp --stdio --profile normal
```

For cross-agent and cross-session tools, use the admin profile:

```bash
super-memory-mcp --stdio --profile admin
```

Equivalent environment form:

```bash
SUPER_MEMORY_MCP_PROFILE=admin super-memory-mcp --stdio
```

The `admin` profile exposes cross-agent/session tools. The `normal` profile intentionally stays narrow.

## 4. Save cross-agent memories

Use `agent_id`, `session_id`, `scope`, and `project` on every write.

Example: Lucas writes a shared decision:

```json
{
  "tool": "super_memory_remember",
  "arguments": {
    "content": "Shared doctrine: canonical markdown remains source of truth.",
    "type": "decision",
    "scope": "shared",
    "agent_id": "lucas",
    "session_id": "discord:1516033294636941462",
    "project": "super-memory",
    "tags": ["cross-agent", "doctrine"]
  }
}
```

Example: Alex writes agent-local implementation context:

```json
{
  "tool": "super_memory_remember",
  "arguments": {
    "content": "Alex verified the plugin config schema for cross-agent memory.",
    "type": "context",
    "scope": "agent-local",
    "agent_id": "alex",
    "session_id": "discord:1516033294636941462",
    "project": "super-memory",
    "tags": ["cross-agent", "config"]
  }
}
```

Recommended scopes:

| Scope | Use for |
| --- | --- |
| `session` | temporary turn/session context |
| `agent-local` | one agent's private work context |
| `shared` | doctrine/preferences/decisions useful to multiple agents |
| `project` | project-level implementation context |
| `cross-agent` | explicit handoffs, comparisons, or inter-agent artifacts |

## 5. Capture cross-session conversation events

Use Honcho-style capture tools for session continuity.

Capture one event:

```json
{
  "tool": "super_memory_capture_event",
  "arguments": {
    "content": "Boss asked Lucas to audit cross-agent memory setup.",
    "session_id": "discord:1516033294636941462",
    "observer_peer_id": "lucas",
    "observed_peer_id": "boss",
    "workspace": "openclaw",
    "source": "discord",
    "metadata": {"channel": "super-memory-github"},
    "analyze": true
  }
}
```

Capture a full user/assistant turn:

```json
{
  "tool": "super_memory_capture_turn",
  "arguments": {
    "user_message": "deep-audit cross-agent memory",
    "assistant_message": "I will inspect docs, tools, tests, and config.",
    "session_id": "discord:1516033294636941462",
    "observer_peer_id": "lucas",
    "observed_peer_id": "boss",
    "analyze": true
  }
}
```

## 6. Query cross-agent memory

List known agents:

```json
{"tool": "super_memory_list_agents", "arguments": {}}
```

Recall one agent's memory:

```json
{
  "tool": "super_memory_cross_agent_recall",
  "arguments": {"query": "plugin config", "agent_id": "alex", "limit": 10}
}
```

Compare agents:

```json
{
  "tool": "super_memory_cross_agent_compare",
  "arguments": {"agent_a": "lucas", "agent_b": "alex", "query": "canonical markdown", "limit": 10}
}
```

Ask Honcho events by observer agent:

```json
{
  "tool": "super_memory_cross_agent_honcho_ask",
  "arguments": {"query": "setup", "observer_agent": "lucas", "about_peer": "boss", "limit": 10}
}
```

## 7. Query cross-session memory

List captured sessions:

```json
{"tool": "super_memory_session_list", "arguments": {"workspace": "openclaw", "limit": 20}}
```

View session timeline:

```json
{
  "tool": "super_memory_session_timeline",
  "arguments": {"session_id": "discord:1516033294636941462", "limit": 50}
}
```

Search all session events:

```json
{
  "tool": "super_memory_session_search",
  "arguments": {"query": "cross-agent", "limit": 20}
}
```

Create and search compressed session archives:

```json
{
  "tool": "super_memory_create_session_summary",
  "arguments": {"session_id": "discord:1516033294636941462", "max_events": 50}
}
```

```json
{
  "tool": "super_memory_search_session_archives",
  "arguments": {"query": "cross-agent", "limit": 20}
}
```

## 8. Use handoff bundles for delegation

Create a handoff:

```json
{
  "tool": "super_memory_create_handoff",
  "arguments": {
    "from_agent": "lucas",
    "to_agent": "alex",
    "title": "Audit cross-agent setup docs",
    "summary": "Check whether setup instructions are complete and verified.",
    "session_id": "discord:1516033294636941462",
    "query": "cross-agent setup",
    "memory_limit": 10,
    "context": {"verification": "run focused tests before reporting"}
  }
}
```

Receiving agent loads the newest open handoff:

```json
{
  "tool": "super_memory_load_current_handoff",
  "arguments": {"agent_id": "alex"}
}
```

Complete with outcome:

```json
{
  "tool": "super_memory_complete_handoff_with_outcome",
  "arguments": {
    "bundle_id": "<bundle_id>",
    "outcome_summary": "Alex completed the setup-doc audit and found no runtime blockers.",
    "created_artifacts_json": ["docs/CROSS_AGENT_SESSION_MEMORY_SETUP.md"],
    "proof_status": "passed"
  }
}
```

## 9. Hybrid cross-scope recall

Use hybrid recall when one query should search across agent/session/layer boundaries.

```json
{
  "tool": "super_memory_cross_scope_recall",
  "arguments": {
    "query": "canonical markdown setup",
    "agent_scope": "all",
    "session_scope": "recent",
    "source_layers": ["markdown", "honcho", "mempalace", "graph"],
    "limit": 20
  }
}
```

Supported filters:

- `agent_scope`: `current`, `agent:<id>`, `all`, `shared`
- `session_scope`: `current`, `session:<id>`, `recent`, `all`
- `source_layers`: `markdown`, `honcho`, `mempalace`, `graph`, or `all`

## 10. Health, audit, and qualification checks

Run these before treating cross-agent/session memory as operational:

```bash
super-memory qualify-cross-agent --config super-memory.yaml
super-memory benchmark-cross-agent --config super-memory.yaml
python scripts/check_tool_contracts.py
python scripts/check_sql_safety.py
python -m pytest \
  tests/test_multi_agent_graph.py \
  tests/test_mcp_server.py \
  tests/test_phase8_contracts.py \
  tests/test_phase8_live_readiness.py \
  tests/test_openclaw_plugin_memory_slot_contract.py \
  tests/test_p0_p5_edge_cases.py \
  tests/test_p0_p5_quality.py -q
```

Live checks through Python:

```bash
python - <<'PY'
from super_memory import bridge
for name, fn in [
    ('cross_layer_health', bridge.cross_layer_health),
    ('diagnostics', bridge.diagnostics),
    ('memory_slot_contract', bridge.memory_slot_contract),
    ('mcp_contract', lambda: bridge.mcp_contract(profile='admin')),
]:
    r = fn()
    print(name, r.get('ok'), r.get('verdict') or r.get('tool_count'))
PY
```

Expected results:

- `check_tool_contracts.py` returns `TOOL_CONTRACTS_OK`
- `check_sql_safety.py` returns `SQL_SAFETY_OK`
- focused tests pass
- `mcp_contract(profile='admin')` reports all admin tools
- `cross_layer_health()` reports no SQLite-only IDs, no content drift, and no orphan projections

## 11. Current caveats

- Runtime auto-capture depends on OpenClaw/plugin hook configuration; manual MCP capture tools are the reliable baseline.
- Cross-agent recall currently uses deterministic SQLite filtering/LIKE, not full semantic embedding ranking.
- Session archive summarization uses deterministic keyword/TF-IDF heuristics, not an LLM by default.
- Handoff bundles are available as tools, but full automatic `sessions_spawn` lifecycle integration is still an operator workflow unless the OpenClaw plugin hooks are explicitly enabled.
- The safe `normal` MCP profile does not expose cross-agent/session tools; use `admin` for these operations.
