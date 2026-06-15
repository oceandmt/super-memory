# Super Memory Architecture

## Design Principles

### 1. Canonical-first save order

Super Memory uses a strict layered save order with **workspace Markdown as the canonical source of truth**:

```
WORKSPACE_MARKDOWN → MEMPALACE → HONCHO → NEURAL_MEMORY
```

**Key behavior:**
- Workspace Markdown is attempted first.
- If workspace Markdown save fails, downstream SQLite-backed layers still save the record.
- Downstream fallback results are marked with `pending_canonical_sync=True` so operators can retry canonical sync later.
- This prevents data loss when workspace paths or permissions are temporarily broken while still preserving canonical-first observability.

**Configuration:**
```python
SuperMemoryConfig(
    require_canonical_first=True  # default: True
)
```

Set `require_canonical_first=False` to run all enabled layers independently without pending-canonical-sync fallback semantics.

### 2. Multi-layer architecture

Each layer serves a specific purpose:

- **Workspace Markdown** — canonical append-only daily notes + curated long-term memory
- **MemPalace** — structured/procedural/project memory with spatial/procedural indexing
- **Honcho** — conversational participant/session memory
- **Neural Memory** — associative/graph/semantic memory with spreading activation

### 3. Safety and guardrails

- Prompt sanitization before save
- Schema normalization
- SQLite safety checks
- No automatic upstream data modification without explicit permission

See `docs/PHASE_*.md` for detailed implementation phases.
