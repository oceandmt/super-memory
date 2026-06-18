# OpenClaw Native Plugin Install Guide

This guide installs the native OpenClaw wrapper in `openclaw-plugin/super-memory` for another OpenClaw instance.

## Install strategy

Super Memory is designed for two surfaces:

1. **OpenClaw native plugin / memory-slot integration.** The long-term OpenClaw target is `exclusive` memory-slot mode, where Super Memory owns the OpenClaw memory slot.
2. **MCP server for non-OpenClaw agents.** MCP agents use `super-memory-mcp --profile normal|admin`; they do not use OpenClaw plugin modes.

For OpenClaw, use a staged rollout:

1. `safe` — additive install/load smoke test.
2. `admin` — additive admin/capture qualification mode; keeps `memory-core` intact while enabling Super Memory tools, turn capture, session/cross-agent workflows, and optional context/flush hooks.
3. `exclusive` — OpenClaw memory-slot cutover mode; use after qualification passes and rollback is understood.

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
super-memory-api
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

### Admin additive/capture mode — recommended qualification mode

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

### Exclusive memory-slot mode — OpenClaw cutover target

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

Bearer auth is disabled by default. If `api_token` is set in YAML, callers must send `Authorization: Bearer <token>`.


If the plugin loads but API calls fail:

```bash
super-memory-api
curl -fsS http://127.0.0.1:8765/health
```

If cross-agent/session workflows fail:

```bash
super-memory qualify-cross-agent --json-out
super-memory benchmark-cross-agent --json-out
super-memory doctor --json-out
```

If the native plugin is still in `safe` or `admin` qualification mode and should not replace `memory-core`, confirm these remain false:

```json
{
  "registerExclusiveMemoryCapability": false,
  "registerLegacyMemoryShims": false
}
```
