# ADR 002: Manifest Strategy for Memory Ingestion

Date: 2026-06-17

Status: Accepted

## Context

Every memory operation (remember, train, import, etc.) must be tracked to
prevent re-ingestion of identical content across multiple calls. Without a
manifest strategy, the same content could be saved repeatedly, bloating the
memory store and triggering cascading recall loops.

## Decision

We use a **content-hash manifest** with SHA-256, stored in a single
SQLite table (`ingest_manifest`). The strategy is:

1. **Pre-Save Deduplication** — Before saving a memory record, hash the
   normalized content (`text.strip().lower()`) with SHA-256.
2. **Write-Ahead Check** — The write flow calls `_manifest_record(store, key=hash, ...)`,
   which returns `False` if the hash already exists in the manifest,
   preventing the duplicate write.
3. **Per-Flow Manifest Tagging** — Each ingestion flow (`train`, `import`,
   `index`, `watch`) tags its manifest entries with a unique `flow` label
   so manifests can be queried per operation type.
4. **Idempotent Writes** — All manifest inserts use `INSERT OR IGNORE`,
   making them safe to run in concurrent or retry scenarios.

## Consequences

- **Positive**: Prevents memory loop explosion; identical content ingested
  from different sources is stored only once.
- **Positive**: Flow tagging enables debugging — you can audit which
  ingestion path populated a given memory.
- **Negative**: The manifest grows linearly with the number of unique
  content hashes. For long-running deployments, a periodic vacuum/cleanup
  process may be needed.

## See Also

- `super_memory/safe_flows.py` — Manifest implementation
- `super_memory/sanitize.py` — Content normalization before hashing
- `super_memory/storage.py` — SuperMemoryStore initialization
