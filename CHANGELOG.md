# Changelog

## 0.2.0 (2026-06-20)

### Fixed

- **Cross-agent turn sync**: Native OpenClaw plugin `agent_end`/`before_agent_finalize` hooks now correctly
  register for all multi-agent instances (Alex, Max, Isol) via Discord `agentChannelMap`.
  Root cause: `api.config` returned global OpenClaw config, not plugin-specific config, causing
  `effectiveAutoSyncTurns = false`. Fix: read from `plugins.entries['super-memory'].config`.
- **Discord content array blocks**: Assistant messages in Discord turn events arrive as array content
  blocks, causing `[object Object]` serialization. Fixed content flattening to extract `text`/`content`
  from each block.
- **Plugin hot-reload**: `SIGUSR1` (coalesced hot reload) does not reload cached JS modules.
  Documentation now recommends `systemctl restart` for plugin code changes.
- **Memory slot activation**: Plugin activation through memory slot now correctly passes config
  (`autoSyncTurns`, `mode`, `agentChannelMap`) via `registerSuperMemoryHooks`.
- **Tool call JSON in assistant reply**: Hook was joining all assistant messages (including
  intermediate tool call JSON). Fixed to take only the **last assistant text message** and strip
  leading JSON lines, so only the final text reply is saved to Super Memory.

### Added

- `agentChannelMap` schema in `openclaw.plugin.json` — Discord channel ID to agent ID routing
- `registerLegacyMemoryTools` flag in plugin config schema
- Content block array flatten helper for multi-block Discord messages
- `hooks.allowConversationAccess` config field for conversation-level access

### Changed

- Plugin file size: 21794 → 25452 bytes (config merge + content flatten + agent routing + tool call filtering)
- `openclaw.plugin.json`: 7358 → 7844 bytes (extended schema)

## 0.1.0 (unreleased)

Initial development release.

### Added

- Python package skeleton with layered local memory architecture
- CLI: `remember`, `recall`, `save-order`, `memory-search`, `memory-get`
- Workspace Markdown append-only daily note backend (canonical layer)
- SQLite deterministic adapters for MemPalace, Honcho, and NeuralMemory layers
- Multi-agent provenance with standard tags (`agent:`, `scope:`, `type:`)
- OpenClaw-compatible search/get shape layer
- OpenClaw plugin wrapper with guarded/non-applied capability skeleton
- MCP stdio server with curated tool profile
- Phase 1–8 feature baselines (guardrails, hardening, intelligence, cognitive orchestration, sandbox backtest, live readiness)
- OpenClaw workspace templates and operator skill
- Full test suite for save order, recall, compatibility, MCP, and guardrails
