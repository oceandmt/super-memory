# Changelog

## 1.5.0 (2026-06-22)

### Added

- **P0 — Foundation**: Entity extraction, memory stage maturation pipeline, consolidation strategies (prune/merge/mature/infer/enrich), hybrid RRF recall fusing 4 layers
- **P1 — Intelligence**: SimHash near-dup detection (64-bit, Hamming ≤3), goal-directed recall bias (1-3x boost), graph query expansion, semantic discovery auto-linking, Bayesian hypothesis engine
- **P2 — Polish**: Leitner spaced repetition auto-seed on save (priority types: DECISION, INSTRUCTION, WORKFLOW, REFERENCE), Knowledge Surface compact prompt context (~500 tokens), abstract storage backend (CoreStorage ABC + SQLiteCoreStorage factory), depth prior adaptive recall depth (0-3 levels)

### Fixed

- `MemoryType` missing `INSTRUCTION` and `REFERENCE` enum values — Leitner auto-seed never triggered for priority types
- `sanitize.py` stale aliases `instruction→doctrine`, `reference→context` causing silent type corruption during save
- `bridge.py` simhash block missing `json` import — every save logged non-blocking error
- **693 orphan graph neurons** referencing soft-deleted memories — cleaned via `graph_cleanup_orphans()` (reduced graph 33%)
- **7 SQLite-only IDs** missing workspace_markdown rows — backfilled

### Changed

- `MemoryType`: 11→13 types (added `instruction`, `reference`)
- `sanitize._TYPE_ALIASES`: removed stale `instruction→doctrine`, `reference→context`; added `ref→reference`, `inst→instruction`
- `bridge.remember()`: integrated SimHash fingerprinting, entity extraction, memory stage assignment, and Leitner auto-seed into save pipeline
- `hybrid_recall.cross_scope_recall()`: integrated depth prior adaptive depth
- `models.py`: extended MemoryType enum, MemoryRecord metadata fields
- `pyproject.toml`: version 1.4.1→1.5.0

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

- Durable Memory Pack for OpenClaw agents: deterministic shared/project memories for Super Memory v0.2.0 fixes, agent roles, cross-agent workflows, recall policy, and memory quality lessons. Available via CLI `super-memory durable-pack`, API `/durable-pack`, and MCP tool `super_memory_durable_pack`, with auto-qualify, debug output, idempotent save, dedupe, status, and audit/fix flows.
- Recall arbitration now falls back to bounded term-wise recall for long multi-term queries so `super_memory_recall_arbitrate` returns context when focused normal recall succeeds. Fallback scoring now boosts `super-memory.durable-pack`, curated durable types, shared/project scope, and high-trust records. Lifecycle duplicate review now filters soft-deleted records and groups by content hash to reduce duplicate scanner noise; `super_memory_lifecycle_quality_cleanup` can soft-delete active duplicates and mark long raw event transcripts for compression without hard deletion.
- Memory-core optimization roadmap foundation: added embedding doctor/auto-select, short-term promotion audit/repair, and deterministic dreaming audit/run/repair flows, exposed through bridge and MCP tools with tests.
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
