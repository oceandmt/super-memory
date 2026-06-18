# OpenClaw Native Plugin Install Guide

This guide installs the native OpenClaw wrapper in `openclaw-plugin/super-memory` for another OpenClaw instance.

## Install strategy

Default recommendation: **admin additive mode**.

Admin additive mode keeps the existing OpenClaw memory slot intact while enabling Super Memory tools, turn capture, session/cross-agent workflows, and optional context/flush hooks. Use exclusive mode only for explicit replacement testing.

## 1. Install Super Memory CLI/API/MCP

```bash
pip install 'git+https://github.com/oceandmt/super-memory.git'
super-memory setup \
  --workspace-root "$HOME/.openclaw/workspace" \
  --output "$HOME/.openclaw/super-memory.yaml" \
  --overwrite
super-memory doctor --no-benchmark --json-out
```

Start the API service:

```bash
super-memory-api --host 127.0.0.1 --port 8765
```

For production, run that command under systemd, pm2, supervisord, or the host service manager.

## 2. Install the native plugin wrapper

From a clone of the repo:

```bash
git clone https://github.com/oceandmt/super-memory.git
cd super-memory
bash scripts/install-openclaw-plugin.sh --mode admin --no-restart
```

The installer copies `openclaw-plugin/super-memory` to `$HOME/.openclaw/plugins/super-memory` by default. Override with:

```bash
OPENCLAW_PLUGINS_DIR=/path/to/plugins bash scripts/install-openclaw-plugin.sh --mode admin --no-restart
```

## 3. Configure OpenClaw

### Safe mode

Additive tools/corpus only.

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

### Admin mode — recommended

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

### Exclusive memory-slot mode — test only

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

## 4. Restart and verify

```bash
openclaw gateway restart
bash scripts/openclaw_plugin_doctor.sh
super-memory doctor --no-benchmark --json-out
curl -fsS http://127.0.0.1:8765/health
```

Expected doctor lines include:

```text
MANIFEST_OK
NODE_CHECK_OK
PLUGIN_DOCTOR_OK
```

## 5. Troubleshooting

If the plugin loads but API calls fail:

```bash
super-memory-api --host 127.0.0.1 --port 8765
curl -fsS http://127.0.0.1:8765/health
```

If cross-agent/session workflows fail:

```bash
super-memory qualify-cross-agent --json-out
super-memory benchmark-cross-agent --json-out
super-memory doctor --json-out
```

If the native plugin should not replace `memory-core`, confirm these remain false:

```json
{
  "registerExclusiveMemoryCapability": false,
  "registerLegacyMemoryShims": false
}
```
