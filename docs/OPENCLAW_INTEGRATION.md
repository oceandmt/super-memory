# OpenClaw Integration Plan

Super Memory should integrate with OpenClaw as a separate local memory app/plugin, not as a fork of `memory-core`.

## OpenClaw memory surfaces to respect

OpenClaw already has multiple memory components:

- `extensions/memory-core/`
  - registers `memory_search`, `memory_get`, `/dreaming`, and `openclaw memory ...` CLI.
  - indexes `MEMORY.md`, `memory/*.md`, optional sessions/wiki corpus via SQLite FTS/BM25/vector hybrid.
  - includes short-term recall promotion and dreaming.
- `packages/memory-host-sdk/`
  - reusable storage/indexing/session-file/embedding runtime integration.
- `extensions/active-memory/`
  - runs a bounded embedded memory subagent on `before_prompt_build`.
  - injects compact hidden recall context into the prompt.
- `extensions/memory-wiki/`
  - deterministic wiki/vault/claims/evidence corpus and supplement tools.
- Skill Workshop
  - governed self-improvement/procedural-memory proposal lifecycle.

## Recommended Super Memory plugin shape

Do **not** replace or fork `memory-core` in v1. Instead:

1. Keep `Workspace Markdown` as canonical local truth.
2. Let existing `memory-core` continue indexing canonical markdown.
3. Run Super Memory as a local sidecar/library as a local sidecar/library.
4. Add an OpenClaw plugin wrapper later that calls the Python app or imports it via a local bridge.

Plugin should use:

- `api.registerMemoryCorpusSupplement(...)`
  - expose Super Memory derived layers as an optional corpus supplement.
- `api.registerMemoryPromptSupplement(...)`
  - inject only a compact digest/status if needed; avoid bloating the system prompt.
- `api.registerTool(...)`
  - `super_memory_remember`
  - `super_memory_recall`
  - `super_memory_get`
  - `super_memory_status`
  - `super_memory_self_improve_candidate`
- `api.on("before_prompt_build", ...)` only if active recall is required.
  - Must use TTL cache, timeout, circuit breaker, and session/channel allowlist.
  - Avoid duplicate work with `active-memory` unless explicitly coordinated.
- `api.runtime.state.openKeyedStore(...)`
  - store plugin cursors, ingest run state, health, and pending promotion metadata.

## OpenClaw-aligned save order

1. **Workspace Markdown**
   - Append `memory/YYYY-MM-DD.md` for session results/events.
   - Promote stable long-term orientation to `MEMORY.md`.
   - Promote doctrine/preferences/blockers/workflows to `memory/registers/`.
   - This is canonical and should succeed before derived layers write.

2. **MemPalace layer**
   - Store verbatim drawer/chunk memory with palace-style metadata.
   - Map OpenClaw lanes/projects/agents to wing/room/hall.
   - Good default mapping:
     - wing = `project:<name>` or `agent:<name>` or `person:<peer>`
     - room = task/topic/session
     - hall = memory type/category
     - drawer = verbatim memory content

3. **Honcho layer**
   - Store peer/session/message/conclusion-like memory.
   - Map OpenClaw agent/session/channel to workspace/peer/session.
   - Use for participant profile, conversation state, and observer/observed multi-agent memory.

4. **Neural Memory layer**
   - Store typed graph/associative memory.
   - Use local deterministic FTS/graph recall first.
   - LLM summarization/consolidation remains optional and pluggable.

## Recall order

For OpenClaw runtime usage:

1. Exact/current canonical facts: use `memory_search`/`memory_get` over markdown first.
2. Super Memory recall: query MemPalace/Honcho/Neural layers for derived context.
3. Verify exact commands/paths/config from source files before action.
4. Inject only compact cited snippets into prompts.

## Self-improvement flow

1. Detect durable lesson/workflow/blocker from a completed task or failure.
2. Save observation/lesson through Super Memory save order.
3. If lesson should become a reusable procedure, create a Skill Workshop proposal rather than editing live skills directly.
4. Only apply/reject/quarantine proposals via governed Skill Workshop actions.
5. Keep provenance: source session, agent, project, confidence, and validation proof.

## Risks and controls

- Avoid running Super Memory active recall and OpenClaw Active Memory simultaneously without timeout/cache coordination.
- Do not let derived SQLite layers outrank canonical markdown.
- Avoid raw secret capture into MemPalace/Honcho/Neural layers.
- Keep embedded LLM off the core remember/recall path.
- Add migrations/schema version before expanding DB structures.
