# OpenClaw Plugin Wrapper

`openclaw-plugin/super-memory/` contains a draft OpenClaw plugin wrapper for the local Super Memory API.

## Runtime shape

1. Start the local API:

```bash
cd projects/super-memory
. .venv/bin/activate
super-memory-api
```

Default URL: `http://127.0.0.1:8765`

2. Register/load the plugin wrapper in OpenClaw once plugin packaging/config is wired.

The wrapper exposes tools:

- `super_memory_remember`
- `super_memory_recall`
- `super_memory_prefetch`
- `super_memory_sync_turn`
- `super_memory_promote`
- `super_memory_status`

## Integration policy

- Workspace Markdown remains canonical local truth.
- The plugin calls the local API; it does not write memory files directly.
- OpenClaw `memory-core` should continue indexing canonical markdown.
- Active prompt injection should be added only after timeout/cache/circuit-breaker rules are implemented.
- Turn auto-sync is default off in the wrapper config until safe channel/session routing is verified.
