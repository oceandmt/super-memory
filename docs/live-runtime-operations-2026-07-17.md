# Super Memory Live Runtime Operations — 2026-07-17

This document records the OpenClaw local live runtime state exported for GitHub.

## Runtime layout

- Config: `/home/oceandmt/.openclaw/super-memory.yaml`
- Main DB: `/home/oceandmt/.openclaw/workspace/data/super-memory.sqlite3`
- Vector DB: `/home/oceandmt/.openclaw/workspace/data/vectors.sqlite3`
- Canonical-first layers: `workspace_markdown`, `mempalace`, `honcho`, `neural_memory`
- Current embedding model/dimension: Ollama `nomic-embed-text`, 768 dimensions

## Exported assets

- Skill: [`SKILLS/super-memory-deep-operations.md`](../SKILLS/super-memory-deep-operations.md)
- Cron export: [`ops/cron/super-memory-live-runtime-cron-jobs.json`](../ops/cron/super-memory-live-runtime-cron-jobs.json)

## Cron policy

The live runtime cron jobs are dry-run-first and non-destructive by default. They avoid stale `super-memory__`/hyphenated tool names and prefer current bridge functions such as:

- `deep_debug`, `deep_audit`, `deep_qualify`, `deep_improve`
- `vector_coverage`
- `layer_parity_audit`, `layer_parity_repair`
- `write_contract_reconcile`, `write_contract_process_jobs`
- `project_backfill`, `project_synapse_backfill`
- `graph_stats`, `closet_stats`, `recall_release_gate`

`hard_delete_soft_deleted` requires explicit approval.

## Last known remediation result

After full DB remediation on 2026-07-17, live runtime verification showed:

- health: ready, not degraded
- deep_debug: 0 problems, 0 warnings
- layer parity: 100% across all four layers
- vector coverage: 100% main DB and external vector DB
- vector dimensions: 100% 768-dim
- embed job backlog: cleared (`done` or `cancelled`)

Project metadata is intentionally not force-filled for memories without enough evidence; some `project=NULL` entries are expected.
