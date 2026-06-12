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

To fully replace `memory-core`, Super Memory still needs an exclusive capability registration:

```js
api.registerMemoryCapability({
  promptBuilder,
  flushPlanResolver,
  runtime,
  publicArtifacts
})
```

The hard part is `runtime.getMemorySearchManager(...)`, which must return an OpenClaw-compatible search manager object. The next implementation step is to inspect/replicate the minimal manager methods expected by `memory_search`, `memory_get`, CLI, status, and prompt systems.

## Guardrail

Until exclusive runtime is implemented and tested, do not disable bundled `memory-core` in a live OpenClaw config. Run Super Memory as additive corpus/tools first.
