# ADR 001: Hook Lifecycle Architecture

Date: 2026-06-17

Status: Accepted

## Context

Super Memory provides a hook system for intercepting memory operations at
multiple lifecycle points. The hooks allow OpenClaw plugins and external
consumers to:

- Capture conversation turns (`post_turn_capture`)
- Validate memory payloads (`before_save`)
- React to memory mutations (`after_save`)
- Inject memory into prompts (`before_prompt`, `after_response`)

## Decision

We structure the hook lifecycle as a **linear pipeline** with the following
phases, executed in order:

```
  BeforePrompt
       ↓
  AfterResponse
       ↓
  PostTurnCapture
       ↓
  Sanitize (non-optional, always applied)
       ↓
  BeforeSave → Save (service.save) → AfterSave
```

### Key Properties

1. **Profile-Dependent Exposure** — Hook tools are only exposed in `admin` and
   `all` MCP profiles. Normal users cannot invoke hook configuration tools.

2. **Fail-Open on Hook Errors** — A failing hook does not abort the save
   pipeline. Errors are logged via structured logging (structlog) and the
   save proceeds as if the hook was not present.

3. **Deduplication at Save Boundary** — The `_manifest_record` function in
   `safe_flows.py` uses SHA-256 content hashing to prevent duplicate
   manifest entries from cascading hook cycles.

4. **Immutable Input** — Hooks must not mutate the memory record in place.
   They must return a new or modified copy of the data they wish to change.

## Consequences

- **Positive**: Extensible by design; external consumers can add monitoring,
  auditing, or enrichment without touching core code.
- **Positive**: Graceful degradation ensures a buggy hook cannot corrupt
  the save pipeline or crash the MCP server.
- **Negative**: Hook execution adds latency on every save/recall operation.
  Future work should include a hook execution timeout and concurrent
  execution for independent hooks.

## See Also

- `super_memory/hooks.py` — HookManager class
- `super_memory/safe_flows.py` — Manifest deduplication logic
- `super_memory/observability.py` — Structured logging integration
