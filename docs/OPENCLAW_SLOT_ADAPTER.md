# OpenClaw Slot Adapter Progress

This document tracks the replacement-path adapter work after Boss clarified Super Memory must become a memory-slot replacement for `memory-core`.

## Implemented now

### Compatibility layer

`super_memory.compat` provides:

- `memory_search_compatible(query, max_results, min_score, corpus, config)`
- `memory_get_compatible(path, from_line, lines, corpus, config)`

These produce stable caller-facing fields similar to OpenClaw `memory_search` / `memory_get`.

### Local API

- `POST /memory-search`
- `POST /memory-get`

### CLI

- `super-memory memory-search <query>`
- `super-memory memory-get <path>`

### OpenClaw additive corpus adapter

The plugin wrapper now registers `api.registerMemoryCorpusSupplement(...)` when the API exists.

### Development-only exclusive capability skeleton

The plugin wrapper also contains a gated `registerMemoryCapability(...)` skeleton behind:

```json
{
  "registerExclusiveMemoryCapability": false
}
```

Default is **false**. This exists only for project development and contract testing. Boss explicitly instructed: develop Super Memory only; do **not** apply it to this machine's OpenClaw runtime/config.

When enabled in a separate test environment, the skeleton provides:

- `promptBuilder`
- `flushPlanResolver: () => null`
- `runtime.getMemorySearchManager(...)`
- a minimal `MemorySearchManager` with:
  - `search(...)`
  - `readFile(...)`
  - `status()`
  - probe/close/sync no-op methods
- empty `publicArtifacts.listArtifacts(...)`

This lets Super Memory act as an additional OpenClaw memory corpus with result objects shaped like:

```js
{
  corpus,
  path,
  title,
  kind,
  score,
  snippet,
  id,
  startLine,
  endLine,
  citation,
  source,
  provenanceLabel,
  sourceType,
  sourcePath
}
```

and get results shaped like:

```js
{
  corpus,
  path,
  title,
  kind,
  content,
  fromLine,
  lineCount,
  id,
  provenanceLabel,
  sourceType,
  sourcePath
}
```

## Why supplement first?

OpenClaw docs show two paths:

- Additive corpus: `registerMemoryCorpusSupplement(...)`
- Exclusive memory slot: `registerMemoryCapability(...)`

The additive corpus bridge is safer and immediately testable because it does not require implementing the internal `MemorySearchManager` runtime contract yet. It is the compatibility stepping stone toward full slot replacement.

## Remaining for true replacement

To fully replace `memory-core`, Super Memory still needs the development skeleton to be hardened into a production exclusive capability registration:

```js
api.registerMemoryCapability({
  promptBuilder,
  flushPlanResolver,
  runtime,
  publicArtifacts
})
```

The hard part is validating `runtime.getMemorySearchManager(...)` under OpenClaw's live memory tools in a safe test install, not on this machine's active OpenClaw runtime.

## Guardrail

Until exclusive runtime is implemented and tested in a separate test environment, do not disable bundled `memory-core` in a live OpenClaw config. For this machine specifically, do not apply Super Memory into OpenClaw at all unless Boss gives a later explicit instruction.
