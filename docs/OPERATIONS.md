# Super Memory Operations Playbook

## Daily health

```bash
super-memory doctor --json-out
super-memory qualify-cross-agent --json-out
super-memory benchmark-cross-agent --json-out
```

## Setup

```bash
super-memory setup \
  --workspace-root /home/oceandmt/.openclaw/workspace \
  --output super-memory.yaml \
  --overwrite
```

## Migration status

```bash
super-memory migrate-status --json-out
```

## Cross-agent/session lifecycle

Session start:

```bash
super-memory qualify-cross-agent --json-out
```

Turn capture uses MCP tools:

- `super_memory_capture_event`
- `super_memory_capture_turn`
- `super_memory_post_turn_capture`

Session end:

- `super_memory_create_session_summary`
- `super_memory_search_session_archives`

## Identity registry

```bash
super-memory entity-upsert agent lucas --alias Lucas --alias lucas-discord --json-out
super-memory entity-resolve Lucas --kind agent --json-out
```

## Prometheus

Run API server, then scrape:

```text
GET /metrics/prometheus
```

## Recommended scheduled jobs

- Every 10 minutes during active development: `super-memory doctor --no-benchmark --json-out`
- Daily: `super-memory doctor --json-out`
- Weekly: `super-memory benchmark-cross-agent --json-out`
- Weekly: `super_memory_graph_cleanup_orphans` dry-run/inspect before destructive cleanup

## Troubleshooting

- `sqlite_only_ids > 0`: run cross-layer health, inspect IDs, then backfill if they are historical markdown-only records.
- `content_drift_count > 0`: compare canonical `workspace_markdown` row to derived layer rows before resolving.
- `qualify-cross-agent` fails on handoff/session archive: inspect `honcho_events`, `handoff_bundles`, and `session_archives` tables.
- Chroma backend unavailable: install `chromadb` or use `sqlite_exact`.
