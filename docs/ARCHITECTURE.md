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
