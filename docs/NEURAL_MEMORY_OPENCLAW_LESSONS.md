# NeuralMemory MCP / OpenClaw Lessons Applied to Super Memory

Boss asked to reference NeuralMemory's OpenClaw memory-slot direction and update Super Memory accordingly.

Source referenced: upstream GitHub repo `nhadaututtheky/neural-memory`, especially:

- `integrations/neuralmemory/src/index.ts`
- `integrations/neuralmemory/src/mcp-client.ts`
- `integrations/neuralmemory/src/tools.ts`
- `integrations/neuralmemory/openclaw.plugin.json`
- `docs/guides/openclaw-plugin.md`

## Lessons pulled forward

### 1. MCP-first capability surface

NeuralMemory's stronger direction was MCP-first:

- direct recall/context/show/session/todo/remember tools
- maintenance/admin tools available but not exposed everywhere
- wrappers remain thin and policy-oriented, not a second full memory system

Super Memory update:

- added stdio MCP server: `super-memory-mcp --stdio`
- MCP tools route through `super_memory.bridge`, keeping API/CLI/MCP behavior aligned
- default profile exposes daily-core memory tools only

### 2. Markdown canon first

NeuralMemory was useful as a durable associative substrate, but OpenClaw doctrine kept local markdown as canonical truth.

Super Memory update:

- MCP instructions state Workspace Markdown remains canonical
- remember still uses Super Memory's canonical-first save order
- derived layers remain programmatic access, not more authoritative than markdown

### 3. Thin orchestration above MCP

NeuralMemory notes showed raw MCP should not decide lane routing, session boundaries, destructive policy, or maintenance cadence by itself.

Super Memory update:

- MCP server is intentionally small
- no hidden OpenClaw apply/register behavior
- no always-on turn capture
- no background daemon started by MCP
- `config_path` supports isolated project tests

### 4. Tool exposure policy by lane/profile

NeuralMemory's lane policy split tools into normal, admin, and advanced/heavy classes.

Super Memory update:

- `normal` MCP profile (default):
  - `super_memory_remember`
  - `super_memory_recall`
  - `super_memory_prefetch`
  - `super_memory_sync_turn`
  - `super_memory_memory_search`
  - `super_memory_memory_get`
  - `super_memory_status`
- `admin` profile:
  - normal tools plus `super_memory_promote`
- `all` profile:
  - every implemented tool

### 5. Memory-slot replacement should be staged

NeuralMemory project notes emphasized staged migration, shadow/parity validation, and no big-bang slot takeover.

Super Memory update:

- OpenClaw plugin has additive corpus supplement first
- exclusive `registerMemoryCapability` skeleton is present but guarded behind:

```json
{
  "registerExclusiveMemoryCapability": false
}
```

- default remains disabled
- this machine's active OpenClaw config is not modified

### 6. Legacy `memory_search` / `memory_get` shims prevent allow-list breakage

Upstream NeuralMemory added backward-compatible shim tools named `memory_search` and `memory_get` because replacing `memory-core` removes the built-in tools while existing OpenClaw tool profiles may still allow-list those names.

Super Memory update:

- plugin wrapper now includes gated shims:
  - `memory_search` → `POST /memory-search`
  - `memory_get` → `POST /memory-get`
- shims are disabled by default via:

```json
{
  "registerLegacyMemoryShims": false
}
```

- shims also turn on automatically if the development-only exclusive slot flag is explicitly enabled:

```json
{
  "registerExclusiveMemoryCapability": true
}
```

This mirrors NeuralMemory's slot-replacement compatibility idea while avoiding conflicts with live `memory-core` on this machine.

### 7. Synchronous fallback registration + async MCP lifecycle

Upstream NeuralMemory registers fallback tools synchronously because OpenClaw freezes tool registration during plugin setup, then starts the MCP subprocess through a service lifecycle.

Super Memory status:

- current plugin uses direct local HTTP API calls, not a managed MCP subprocess yet
- MCP server exists project-locally (`super-memory-mcp --stdio`)
- future project-only hardening can add a TS MCP client/subprocess lifecycle similar to NeuralMemory

## Current Super Memory position

Super Memory now has three project-local integration surfaces:

1. CLI/API for local development
2. MCP stdio server for MCP-compatible agents
3. OpenClaw plugin wrapper with additive corpus + disabled capability skeleton

This supports development toward memory-slot replacement without applying it to the current OpenClaw installation.

## Next project-only hardening targets

- Add richer MCP resources for architecture/status/capabilities.
- Add MCP prompts/templates for recall, session-end capture, and promotion review.
- Add contract tests for OpenClaw `MemorySearchManager` shape without running against this machine's live OpenClaw config.
- Add parity fixtures comparing CLI/API/MCP outputs.
- Add security/privacy filter before broad derived-layer writes.
- Add optional TypeScript MCP subprocess client in the OpenClaw plugin wrapper, modeled after upstream NeuralMemory's `mcp-client.ts`, but keep it disabled/not applied on this machine.
