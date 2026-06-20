# Super Memory OpenClaw Native Plugin

This directory is the native OpenClaw plugin wrapper for Super Memory. Super Memory is intended to be able to run as OpenClaw's memory slot, but the wrapper is intentionally safe by default: it runs as an additive tools/corpus plugin unless you explicitly opt into `exclusive` memory-slot mode.

## Recommended install mode

Use **admin additive/capture mode** for other OpenClaw installations first. It enables Super Memory tools, turn capture, optional context, and flush hooks without replacing `memory-core`. Promote to `exclusive` only after qualification when you want Super Memory to own the OpenClaw memory slot.

## Prerequisites

```bash
pip install 'git+https://github.com/oceandmt/super-memory.git'
super-memory setup --workspace-root "$HOME/.openclaw/workspace" --output "$HOME/.openclaw/super-memory.yaml" --overwrite
super-memory doctor --no-benchmark --json-out
super-memory-api --host 127.0.0.1 --port 8765
```

## Local plugin install

From the repository root:

```bash
bash scripts/install-openclaw-plugin.sh --mode admin --no-restart
```

Or copy manually:

```bash
mkdir -p "$HOME/.openclaw/plugins"
rsync -a --delete openclaw-plugin/super-memory/ "$HOME/.openclaw/plugins/super-memory/"
```

## Modes

### safe

Additive tools/corpus only. Minimal hooks.

```json
{
  "plugins": {
    "super-memory": {
      "mode": "safe",
      "apiBaseUrl": "http://127.0.0.1:8765",
      "registerExclusiveMemoryCapability": false,
      "registerLegacyMemoryShims": false
    }
  }
}
```

### admin

Recommended cross-agent/cross-session mode. Keeps memory-core intact.

```json
{
  "plugins": {
    "super-memory": {
      "mode": "admin",
      "apiBaseUrl": "http://127.0.0.1:8765",
      "autoSyncTurns": true,
      "autoContext": false,
      "autoFlush": true,
      "startupConsolidation": false,
      "agentId": "lucas",
      "toolProfile": "admin",
      "registerExclusiveMemoryCapability": false,
      "registerLegacyMemoryShims": false
    }
  }
}
```

### exclusive

OpenClaw memory-slot cutover mode. Replaces OpenClaw's memory slot and can register legacy `memory_search`/`memory_get` shims. Use after staged qualification, not as the first install smoke test.

```json
{
  "plugins": {
    "slots": { "memory": "super-memory" },
    "super-memory": {
      "mode": "exclusive",
      "apiBaseUrl": "http://127.0.0.1:8765",
      "registerExclusiveMemoryCapability": true,
      "registerLegacyMemoryShims": true,
      "autoSyncTurns": true,
      "autoContext": true,
      "autoFlush": true
    }
  }
}
```

## Verify

```bash
bash scripts/openclaw_plugin_doctor.sh
super-memory doctor --no-benchmark --json-out
curl -fsS http://127.0.0.1:8765/health
```

## Troubleshooting

If OpenClaw logs `Super Memory API health check failed`, start the API first:

```bash
super-memory-api --host 127.0.0.1 --port 8765
```

If tools load but recall is empty, run:

```bash
super-memory doctor --json-out
super-memory qualify-cross-agent --json-out
```
