#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLUGIN_DIR="${OPENCLAW_SUPER_MEMORY_PLUGIN_DIR:-$REPO_ROOT/openclaw-plugin/super-memory}"
API_URL="${SUPER_MEMORY_API_BASE_URL:-http://127.0.0.1:8765}"
PY="${PYTHON:-python3}"

echo "═══ Super Memory OpenClaw Plugin Doctor ═══"
echo "Plugin dir: $PLUGIN_DIR"
echo "API URL: $API_URL"

[ -d "$PLUGIN_DIR" ] || { echo "FAIL plugin directory missing"; exit 2; }
[ -f "$PLUGIN_DIR/openclaw.plugin.json" ] || { echo "FAIL openclaw.plugin.json missing"; exit 2; }
[ -f "$PLUGIN_DIR/index.js" ] || { echo "FAIL index.js missing"; exit 2; }
[ -f "$PLUGIN_DIR/mcp-client.js" ] || { echo "FAIL mcp-client.js missing"; exit 2; }

$PY - <<PY
import json
from pathlib import Path
p = Path('$PLUGIN_DIR') / 'openclaw.plugin.json'
d = json.loads(p.read_text())
assert d.get('id') == 'super-memory'
assert d.get('kind') == 'memory'
props = d['configSchema']['jsonSchema']['properties']
for key in ['mode', 'apiBaseUrl', 'autoSyncTurns', 'autoContext', 'autoFlush', 'registerExclusiveMemoryCapability', 'registerLegacyMemoryShims']:
    assert key in props, key
assert props['mode']['default'] == 'safe'
assert props['registerExclusiveMemoryCapability']['default'] is False
assert props['registerLegacyMemoryShims']['default'] is False
print('MANIFEST_OK tools=%s mode_default=%s' % (len(d.get('contracts', {}).get('tools', [])), props['mode']['default']))
PY

node --check "$PLUGIN_DIR/index.js"
node --check "$PLUGIN_DIR/mcp-client.js"
echo "NODE_CHECK_OK"

if command -v super-memory >/dev/null 2>&1; then
  super-memory doctor --no-benchmark --json-out >/dev/null && echo "SUPER_MEMORY_DOCTOR_OK" || echo "SUPER_MEMORY_DOCTOR_WARN"
else
  echo "SUPER_MEMORY_CLI_WARN super-memory command not found"
fi

if command -v curl >/dev/null 2>&1; then
  if curl -fsS "$API_URL/health" >/dev/null 2>&1; then
    echo "API_HEALTH_OK"
  else
    echo "API_HEALTH_WARN start API with: super-memory-api --host 127.0.0.1 --port 8765"
  fi
fi

echo "PLUGIN_DOCTOR_OK"
