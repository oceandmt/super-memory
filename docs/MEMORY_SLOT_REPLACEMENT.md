# Super Memory as OpenClaw Memory-Slot Replacement

Boss clarified that Super Memory is not merely a sidecar. It is intended to become the main OpenClaw memory-slot replacement for `memory-core`, crystallizing the strongest ideas from Hermes, MemPalace, Honcho, NeuralMemory, and OpenClaw memory internals.

## Target role

Super Memory should eventually provide the active OpenClaw memory capability:

- memory search
- memory get/read
- prompt memory section
- flush/capture plan
- runtime/session capture
- corpus artifacts
- self-improvement/procedural memory promotion

## Current replacement-path implementation

Implemented in this stage:

- `super_memory.compat.memory_search_compatible(...)`
  - returns `memory_search`-style payload fields:
    - `results`
    - `path`
    - `startLine`
    - `endLine`
    - `score`
    - `textScore`
    - `snippet`
    - `source`
    - `corpus`
- `super_memory.compat.memory_get_compatible(...)`
  - reads:
    - `super-memory://<layer>/<memory_id>` virtual paths
    - workspace markdown file excerpts
- API endpoints:
  - `POST /memory-search`
  - `POST /memory-get`
- CLI commands:
  - `super-memory memory-search ...`
  - `super-memory memory-get ...`
- Plugin wrapper tools:
  - `super_memory_search_compatible`
  - `super_memory_get_compatible`

## OpenClaw SDK direction

OpenClaw docs indicate the preferred exclusive memory plugin API is:

```js
api.registerMemoryCapability(capability)
```

Legacy-compatible APIs include:

```js
api.registerMemoryPromptSection(...)
api.registerMemoryFlushPlan(...)
api.registerMemoryRuntime(...)
```

Additive helpers remain available:

```js
api.registerMemoryPromptSupplement(...)
api.registerMemoryCorpusSupplement(...)
```

## Next implementation target

The next step after compatibility shape is a real memory capability registration layer:

1. Build a JS adapter around Super Memory API.
2. Register Super Memory via `registerMemoryCapability` when plugin runtime shape is confirmed.
3. Provide promptBuilder from `/prefetch` or `/memory-search`.
4. Provide runtime methods for search/get/capture/flush.
5. Keep canonical Workspace Markdown first and let OpenClaw still read exact source files.

## Non-goals for the current stage

- Not yet replacing OpenClaw bundled `memory-core` in running config.
- Not yet enabling active prompt injection by default.
- Not yet implementing a full clone of memory-core embedding/index internals.

## Guardrails

- Derived layers must not outrank canonical markdown.
- Exact values/paths/configs must still be verified from source files.
- Raw secrets should not be captured into derived layers.
- Embedded LLM remains optional.
