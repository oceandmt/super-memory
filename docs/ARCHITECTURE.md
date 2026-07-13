# Super Memory Architecture

Super Memory is a local, non-Docker, multi-layer memory app for OpenClaw multi-agents.

## Goals

- Make Workspace Markdown the canonical local truth for OpenClaw memory.
- Add deterministic local adapters for MemPalace, Honcho, and NeuralMemory-style memory functions.
- Preserve provenance and multi-agent routing tags on every write.
- Keep embedded LLM usage optional, not required for baseline remember/recall.
- Support remember + self-improve workflows for Lucas/Alex/Max/Isol style agents.

## Layer model

### Layer 01: Workspace Markdown

Canonical local truth. This layer writes append-only daily notes under `memory/YYYY-MM-DD.md` and can later promote stable doctrine/preferences/blockers into `MEMORY.md` or `memory/registers/`.

This layer must save first. Other layers are derived/adaptive memory surfaces.

### Layer 02: MemPalace

Structured local memory inspired by palace/room/entity/procedure organization. Current implementation is a deterministic SQLite adapter with normalized tags and FTS recall. Future adapter can map memories into palace objects without changing the Super Memory API.

Best for:
- agent working rooms
- task/project chambers
- procedural memory
- self-improvement lessons

### Layer 03: Honcho

Conversational/session/participant memory layer. Current implementation is a deterministic SQLite adapter. Future adapter can call Honcho APIs or local Honcho stores.

Best for:
- participant profile facts
- session turns
- preferences inferred from dialogue
- multi-agent conversational state

### Layer 04: Neural Memory

Associative graph/semantic recall layer. Current implementation is a deterministic SQLite adapter and does not require embedded LLM. Future adapter can call neural-memory MCP/local APIs when available.

Best for:
- associative recall
- cross-time blockers/workflows
- hypotheses/insights
- graph-style relationships

## Save order

1. Workspace Markdown: append canonical event/result.
2. MemPalace: store structured procedural/project memory.
3. Honcho: store conversational participant/session memory.
4. Neural Memory: store associative recall memory.

If Workspace Markdown fails and `require_canonical_first=true`, downstream layers are skipped to prevent derived layers from becoming more authoritative than canonical local truth.

## Required provenance tags

Every saved memory should include:

- `agent:<lucas|alex|max|isol|...>`
- `scope:<session|agent-local|shared|project|cross-agent>`
- `type:<decision|doctrine|preference|blocker|workflow|lesson|...>`
- `project:<name>` when project-specific

## Self-improvement workflow

1. Capture a result, failure, blocker, or lesson as `type=lesson|workflow|blocker|decision`.
2. Save canonical markdown first.
3. Save procedural/project form to MemPalace.
4. Save conversation/person/session implications to Honcho when relevant.
5. Save associative summary to Neural Memory.
6. Promote stable rules to `memory/registers/` or a Skill Workshop proposal when they should become standing procedure.

## OpenClaw integration points

- CLI: `super-memory remember ...` for local scripts/hooks.
- Python API: `SuperMemoryService.save(MemoryRecord(...))`.
- Future OpenClaw plugin: call this service after Boss-facing durable turns or agent run completion.
- Future MCP server: expose `remember`, `recall`, `save_order`, and `promote` tools.

## Write Contract (`write_contract/`)

Every canonical save registers an outbox entry via `write_contract.register_memory()` (called from `service.py` for both the initial `workspace_markdown` save and each derived-layer save):

- `memory_fingerprints`: `(memory_id, layer)` → normalized hash + simhash, used for duplicate detection.
- `memory_write_intents`: idempotency ledger keyed on a `source_event_key` built from adapter metadata (`message_id`/`event_id` + chat/session context). Only populated when that metadata is present — most direct/CLI saves will not have a `message_id`, so a low row count here is expected, not a failure.
- `memory_jobs`: async job queue (currently `embed` jobs) drained by the write-contract worker; `write_contract_reconcile()` / `write_contract_process_jobs()` are exposed as bridge/MCP maintenance tools.

Any code path that inserts directly into `memories` outside `service.save()` (e.g. `handoff.py::complete_handoff_with_outcome`) must still compute and store `content_hash` itself — downstream dedup, drift-repair, and cross-layer projection joins all key on it, and a NULL hash silently drops the row out of `NOT IN (SELECT content_hash ...)`-style checks.

## Dream Engine (`dream.py`, `dream_engine.py`)

Idle-time consolidation with three phases: surprisal ranking, cross-session pattern/bridge detection, and insight generation. Candidates pass through a quality gate (`quality_scorer.score_memory`, min 0.5) and a dedup check against existing dream insights before being saved as `type=insight, agent_id="dream-engine"` memories.

A shared `_is_dream_noise()` guard (in `dream.py`, imported by `dream_engine.py`) rejects two failure modes before save: candidates whose only shared signal is an ambient/generic token (license, copyright, software, python, ...), and candidates that echo known prompt-injection text. Raw token-frequency statistics ("'X' appears in N memories") are computed for the pattern-summary phase's report output but are never persisted as memories — they are metrics, not insights.
