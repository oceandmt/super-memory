# Super Memory Phases 2–4

Status: project-only implementation. Do not apply/register into this machine's active OpenClaw runtime/config unless Boss explicitly requests it later.

## Consistency invariant

Super Memory must keep the memory layers combined without making derived layers authoritative:

1. Workspace Markdown stays canonical local truth.
2. MemPalace, Honcho, and NeuralMemory-style layers remain downstream projections.
3. If canonical-first save is required and canonical save fails, downstream writes are skipped.
4. Advanced tools may add metadata/events, but must not silently rewrite canonical memory.

## Phase 2 — Memory-slot hardening

Implemented baseline:

- `openclaw-plugin/super-memory/mcp-client.js`: subprocess MCP client compatible with JS/TS runtimes.
- `/mcp-tools`: dynamic tools/list proxy endpoint.
- guarded plugin hook skeletons behind `registerSuperMemoryHooks=true`:
  - pre-prompt context
  - post-agent capture
  - pre-compaction flush
  - reset flush
  - startup consolidation
- contract tests for `memory_search`, `memory_get`, dynamic tools/list, and plugin/client syntax.

## Phase 3 — Advanced memory intelligence

Implemented deterministic baseline tools:

- conflicts
- provenance
- source
- version
- pin
- consolidate
- gaps
- explain
- situation
- reflex
- boundaries

These provide safe audit/event records and read-only summaries where appropriate. Heavy model-backed reasoning can be added later behind explicit configuration.

## Phase 4 — Heavy/optional

Implemented disabled-safe skeletons for:

- train/import/index
- cloud sync
- Telegram backup
- visualize
- store/community brain
- watch directory daemon

These return `enabled=false` by default. They must not start daemons, perform network sync, import documents, or upload backups without explicit future configuration.
