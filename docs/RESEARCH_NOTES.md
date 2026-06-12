# Research Notes

Status: initial implementation scaffold created while source-level research runs in parallel.

## Repositories to analyze

- `openclaw/openclaw`: focus on memory system, self-improvement system, config, plugin/session architecture.
- `nousresearch/hermes-agent`: base inspiration for multi-layer memory architecture.
- `nhadaututtheky/neural-memory`: use as associative/graph layer inspiration, but avoid heavy embedded LLM dependency.
- `plastic-labs/honcho`: use as participant/session/conversation memory inspiration.
- `MemPalace/mempalace`: use as palace/room/procedural memory inspiration.

## Current implementation assumptions

Until source-level mapping is complete, Super Memory exposes stable local abstractions:

- `MemoryRecord`: normalized cross-layer memory payload.
- `MemoryBackend`: layer adapter interface.
- `SuperMemoryService`: ordered save/recall orchestrator.
- SQLite fallback adapters: deterministic local implementation for derived layers.

This lets OpenClaw use Super Memory locally now, while deeper upstream-compatible adapters can replace the fallback backends later.

## Design constraints from Boss

- Local app, no Docker containers.
- Use Hermes memory system as the root design inspiration.
- Layer order:
  1. Workspace Markdown
  2. MemPalace memory functions
  3. Honcho memory functions
  4. Neural Memory functions
- Provide concrete save memory order per layer.
- Focus on remember and self-improve for multi-agents.
- Do not depend heavily on embedded LLM like `nhadaututtheky/neural-memory`.
