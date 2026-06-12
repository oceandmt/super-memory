# Super Memory MCP Server

Super Memory includes a local stdio MCP server so MCP-compatible agents can use it directly, similar in spirit to `neural-memory` MCP tooling, while still preserving Super Memory's canonical-first design.

## Important guardrail

This is **project development only**. Do not apply/register this MCP server into this machine's active OpenClaw config unless Boss explicitly gives a later instruction.

## Run

From the project virtualenv:

```bash
super-memory-mcp --stdio
```

Safe default profile:

```bash
super-memory-mcp --stdio --profile normal
```

Admin/development profile:

```bash
super-memory-mcp --stdio --profile admin
```

Environment equivalent:

```bash
SUPER_MEMORY_MCP_PROFILE=admin super-memory-mcp --stdio
```

Equivalent module form:

```bash
python -m super_memory.mcp_server --stdio
```

The server speaks newline-delimited JSON-RPC over stdio.

## MCP methods

Supported protocol methods:

- `initialize`
- `notifications/initialized`
- `ping`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/read`

## Tools

Super Memory follows the NeuralMemory MCP lesson: expose a narrow daily-core tool surface by default and keep structural/admin actions behind an explicit profile.

Profiles:

- `normal` default: remember, recall, prefetch, sync-turn, memory-search, memory-get, status
- `admin`: normal tools plus promotion
- `all`: every implemented tool

### `super_memory_remember`

Save memory through Super Memory canonical-first layer order.

Args include:

- `content` required
- `type`
- `scope`
- `agent_id`
- `session_id`
- `project`
- `tags`
- `source`
- `trust_score`
- `metadata`
- `config_path`

### `super_memory_recall`

Recall from all Super Memory layers.

Args:

- `query` required
- `limit`
- `config_path`

### `super_memory_prefetch`

Merged/deduped prompt prefetch recall.

Args:

- `query` required
- `limit`
- `config_path`

### `super_memory_sync_turn`

Save compact multi-agent conversation turn memory.

Args:

- `agent_id`
- `session_id`
- `user_message`
- `assistant_message`
- `project`
- `metadata`
- `config_path`

### `super_memory_memory_search`

OpenClaw `memory_search`-compatible result payload.

Args:

- `query` required
- `max_results`
- `min_score`
- `corpus`
- `config_path`

### `super_memory_memory_get`

OpenClaw `memory_get`-compatible read from virtual Super Memory paths or workspace markdown files.

Args:

- `path` required
- `from_line`
- `lines`
- `corpus`
- `config_path`

### `super_memory_promote`

Promote an item into `MEMORY.md` and matching register.

Profile: `admin` / `all` only.

Args:

- `memory_id` required
- `config_path`

### `super_memory_status`

Return local status and counts.

Args:

- `config_path`

## Resource

### `super-memory://status`

Returns Super Memory status as JSON.

## Example JSON-RPC

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
```

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
```

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"super_memory_status","arguments":{}}}
```

## Design notes

- No Docker.
- No embedded LLM required for baseline remember/recall.
- Tools route through `super_memory.bridge`, so API/CLI/MCP behavior stays aligned.
- `config_path` allows isolated test configs without touching the active workspace DB.
