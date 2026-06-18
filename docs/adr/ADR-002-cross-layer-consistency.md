# ADR-002: Cross-Layer Memory Consistency

**Status:** Accepted  
**Date:** 2026-06-18  
**Author:** Lucas (super-memory project)

## Context

Super Memory has a four-layer architecture:
1. **Workspace Markdown** — canonical filesystem store (`memory/YYYY-MM-DD.md`)
2. **MemPalace** — spatial/procedural/project memory (SQLite)
3. **Honcho** — conversation/participant/session memory (SQLite)  
4. **Neural Memory** — associative/graph/cognitive memory (SQLite)

Prior to this ADR, the `WorkspaceMarkdownBackend.save()` wrote only to the filesystem (append line to daily `.md` file) and did NOT write a `workspace_markdown` row to the shared SQLite `memories` table. The SQLite layers (mempalace, honcho, neural_memory) each wrote their own rows.

This created a split-channel model where:
- 21.3% of memory IDs existed only in workspace_markdown (filesystem)
- 78.7% existed only in SQLite (mempalace+honcho+neural_memory)
- **0%** had full 4-layer representation in a single query
- `status()` undercounted total memories
- Cross-layer content fidelity could not be verified

## Decision

**The `SuperMemoryService.save()` method now additionally writes a `workspace_markdown` row into the shared SQLite `memories` table after a successful filesystem markdown write.** This row is a **derived mirror** — filesystem markdown remains the canonical source. The SQLite workspace_markdown row exists solely for visibility and cross-layer health monitoring.

Additionally:
- **Content hash** (SHA-256) is computed at save time and stored in `memories.content_hash` for drift detection
- **`status()`** now reports `filesystem_markdown` counts alongside SQLite layers
- **`cross_layer_health()`** endpoint verifies: SQLite-only IDs, content drift, orphan projections, and full 4-layer coverage
- **`backfill_markdown_sqlite()`** provides one-shot backfill for historical IDs

## Consequences

### Positive
- Single SQL query can now see all 4 layers for any memory ID
- `status()` provides complete picture (SQLite + filesystem)
- Cross-layer health can be automated (audit detects gaps)
- Content hash enables drift detection across layers
- New records achieve 100% 4-layer coverage

### Negative
- Slightly larger SQLite table (one extra row per memory record)
- Write latency increases marginally (~50-100ms) due to additional INSERT
- 500 historical benchmark-only records lack SQLite workspace_markdown rows (backfill handled via `backfill_markdown_sqlite`)

### Neutral
- Canonical-first invariant preserved: filesystem markdown remains master
- Workspace markdown SQLite rows are marked with `content_hash` for drift detection
- If SQLite mirror write fails, save still succeeds with a log warning
