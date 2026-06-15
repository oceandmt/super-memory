# Super Memory Architecture

## Design Principles

### 1. Canonical-first save order

Super Memory uses a strict layered save order with **workspace Markdown as the canonical source of truth**:

```
WORKSPACE_MARKDOWN → MEMPALACE → HONCHO → NEURAL_MEMORY
```

**Key behavior:**
- If workspace Markdown save fails, downstream layers are skipped by default
- This prevents derived layers from containing data that isn't in the canonical layer
- Trade-off: Better data consistency vs. potential "nothing saved" on permission/path errors

**Configuration:**
```python
SuperMemoryConfig(
    require_canonical_first=True  # default: True
)
```

Set `require_canonical_first=False` to allow downstream layers to save even when Markdown fails (not recommended for production).

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
