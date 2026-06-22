#!/usr/bin/env bash
set -euo pipefail

# Super Memory OpenClaw Plugin Installer
# Usage:
#   bash scripts/install-openclaw-plugin.sh [--mode safe|admin|exclusive] [--plugins-dir DIR] [--restart|--no-restart] [--dry-run]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLUGIN_SRC="$REPO_ROOT/openclaw-plugin/super-memory"
DEFAULT_PLUGINS_DIR="$HOME/.openclaw/plugins"
MODE="admin"
RESTART="ask"
DRY_RUN="no"
PLUGINS_DIR="${OPENCLAW_PLUGINS_DIR:-$DEFAULT_PLUGINS_DIR}"

while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE="${2:-}"; shift 2 ;;
    --plugins-dir) PLUGINS_DIR="${2:-}"; shift 2 ;;
    --restart) RESTART="yes"; shift ;;
    --no-restart) RESTART="no"; shift ;;
    --dry-run) DRY_RUN="yes"; shift ;;
    -h|--help)
      sed -n '1,20p' "$0"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

case "$MODE" in
  safe|admin|exclusive) ;;
  *) echo "Invalid --mode '$MODE'. Expected safe, admin, or exclusive." >&2; exit 2 ;;
esac

command_exists() { command -v "$1" >/dev/null 2>&1; }

echo "═══ Super Memory Plugin Installer ═══"
echo "Mode: $MODE"
echo "Plugin target: $PLUGINS_DIR/super-memory"
echo ""

if ! command_exists openclaw; then
  echo "⚠️  openclaw CLI not found. Continuing with local plugin copy only."
else
  echo "✅ openclaw CLI found: $(openclaw --version 2>/dev/null || echo ok)"
  # Check version compatibility (expecting 0.10.x or later)
  OC_VERSION=$(openclaw --version 2>/dev/null | grep -oP '\d+\.\d+\.\d+' | head -1)
  if [ -n "$OC_VERSION" ]; then
    OC_MAJOR=$(echo "$OC_VERSION" | cut -d. -f1)
    OC_MINOR=$(echo "$OC_VERSION" | cut -d. -f2)
    if [ "$OC_MAJOR" -lt 1 ] && [ "$OC_MINOR" -lt 10 ]; then
      echo "⚠️  OpenClaw version $OC_VERSION < 0.10 — plugin slot may not work correctly"
    fi
  fi
fi

if ! command_exists super-memory; then
  echo "⚠️  super-memory CLI not found. Install first:"
  echo "    pip install 'git+https://github.com/oceandmt/super-memory.git'"
elif ! super-memory --help >/dev/null 2>&1; then
  echo "⚠️  super-memory CLI installed but not working correctly"
else
  echo "✅ super-memory CLI found: $(super-memory --version 2>/dev/null || echo ok)"
fi

if [ "$DRY_RUN" = "yes" ]; then
  echo "🏁 Dry-run mode — would install plugin from:"
  echo "   Source: $PLUGIN_SRC"
  echo "   Target: $PLUGINS_DIR/super-memory"
  echo "   Mode:   $MODE"
  echo "   Files:  $(find "$PLUGIN_SRC" -type f | wc -l)"
  echo "🏁 Dry-run complete — no files changed"
  exit 0
fi

mkdir -p "$PLUGINS_DIR/super-memory"
echo "📦 Copying plugin files..."
rsync -a --delete "$PLUGIN_SRC/" "$PLUGINS_DIR/super-memory/"

python3 - <<PY
import json
from pathlib import Path
p = Path('$PLUGINS_DIR/super-memory/openclaw.plugin.json')
d = json.loads(p.read_text())
assert d.get('id') == 'super-memory'
assert d.get('kind') == 'memory'
print('✅ manifest verified: %s tools declared' % len(d.get('contracts', {}).get('tools', [])))
PY

if command_exists node; then
  node --check "$PLUGINS_DIR/super-memory/index.js" >/dev/null 2>&1
  node --check "$PLUGINS_DIR/super-memory/mcp-client.js" >/dev/null 2>&1
  echo "✅ node syntax checks passed"
else
  echo "⚠️  node not found — skipping JS syntax check"
fi

if command_exists openclaw; then
  openclaw plugins enable super-memory 2>/dev/null || echo "⚠️  'openclaw plugins enable' unavailable or failed; configure manually if needed."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Plugin installed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Recommended prerequisite service:"
echo "  pip install 'git+https://github.com/oceandmt/super-memory.git'"
echo "  super-memory setup --workspace-root \"$HOME/.openclaw/workspace\" --output \"$HOME/.openclaw/super-memory.yaml\" --overwrite"
echo "  super-memory-api --host 127.0.0.1 --port 8765"
echo ""
echo "Suggested OpenClaw config for mode=$MODE:"
case "$MODE" in
  safe)
    cat <<'EOF'
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
EOF
    ;;
  admin)
    cat <<'EOF'
{
  "plugins": {
    "super-memory": {
      "mode": "admin",
      "apiBaseUrl": "http://127.0.0.1:8765",
      "autoSyncTurns": true,
      "autoContext": false,
      "autoFlush": true,
      "startupConsolidation": false,
      "toolProfile": "admin",
      "registerExclusiveMemoryCapability": false,
      "registerLegacyMemoryShims": false
    }
  }
}
EOF
    ;;
  exclusive)
    cat <<'EOF'
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
EOF
    ;;
esac

echo ""
echo "Verify:"
echo "  bash scripts/openclaw_plugin_doctor.sh"
echo "  super-memory doctor --no-benchmark --json-out"
echo ""

if [ "$RESTART" = "ask" ] && command_exists openclaw; then
  read -rp "Restart OpenClaw gateway now? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] && RESTART="yes" || RESTART="no"
fi
if [ "$RESTART" = "yes" ]; then
  openclaw gateway restart
fi

echo "═══ Done ═══"
