#!/usr/bin/env bash
set -euo pipefail

# ─── Super Memory OpenClaw Plugin Installer ────────────────────────────────
# One-shot script to install & activate the Super Memory plugin into
# a running OpenClaw Gateway on this machine.
#
# Usage:
#   bash scripts/install-openclaw-plugin.sh
#
# What it does:
#   1. Checks OpenClaw CLI & plugin dir
#   2. Copies plugin wrapper into OpenClaw plugins/
#   3. Enables the plugin
#   4. Shows activation config options (exclusive slot vs additive)
#   5. Optionally restarts gateway
# ───────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLUGIN_SRC="$REPO_ROOT/openclaw-plugin/super-memory"
DEFAULT_PLUGINS_DIR="$HOME/.openclaw/plugins"

echo "═══ Super Memory Plugin Installer ═══"
echo ""

# ── Check OpenClaw CLI ─────────────────────────────────────────────────────
if ! command -v openclaw &>/dev/null; then
    echo "❌ openclaw CLI not found. Install OpenClaw first: https://docs.openclaw.ai"
    exit 1
fi
echo "✅ openclaw CLI found: $(openclaw --version 2>/dev/null || echo 'ok')"

# ── Resolve plugin target dir ──────────────────────────────────────────────
PLUGINS_DIR="${OPENCLAW_PLUGINS_DIR:-$DEFAULT_PLUGINS_DIR}"
mkdir -p "$PLUGINS_DIR/super-memory"
echo "📁 Plugin target: $PLUGINS_DIR/super-memory"

# ── Copy plugin wrapper ────────────────────────────────────────────────────
echo "📦 Copying plugin files..."
rsync -a --delete "$PLUGIN_SRC/" "$PLUGINS_DIR/super-memory/"
echo ""

# ── Verify plugin manifest ─────────────────────────────────────────────────
if [ ! -f "$PLUGINS_DIR/super-memory/openclaw.plugin.json" ]; then
    echo "❌ openclaw.plugin.json missing in plugin dir"
    exit 2
fi
TOOL_COUNT=$(python3 -c "import json; print(len(json.load(open('$PLUGINS_DIR/super-memory/openclaw.plugin.json'))['contracts']['tools']))" 2>/dev/null || echo "?")
echo "   ✓ openclaw.plugin.json verified ($TOOL_COUNT tools declared)"

# ── Enable plugin ──────────────────────────────────────────────────────────
echo ""
echo "🔌 Enabling super-memory plugin..."
openclaw plugins enable super-memory 2>/dev/null || echo "   ⚠️  'plugins enable' not supported in this CLI version — skip"

# ── Config guidance ────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ Plugin installed & copied"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "▶ Activation modes (pick ONE):"
echo ""
echo "  MODE A — ADDITIVE (safer, recommended for testing):"
echo "    openclaw config patch plugins.entries.super-memory.enabled=true"
echo "    → Tools appear alongside existing memory tools"
echo ""
echo "  MODE B — EXCLUSIVE SLOT (replaces memory-core):"
echo "    openclaw config patch plugins.slots.memory=super-memory"
echo "    openclaw config patch plugins.entries.super-memory.registerExclusiveMemoryCapability=true"
echo "    → Super Memory becomes THE memory provider"
echo ""
echo "  MODE C — LEGACY SHIMS (additive + memory_search shims):"
echo "    openclaw config patch plugins.entries.super-memory.registerLegacyMemoryShims=true"
echo "    → memory_search/memory_get shimmed through Super Memory API"
echo ""
echo "▶ After config:"
echo "    openclaw gateway restart"
echo ""
echo "▶ Verify:"
echo "    openclaw plugins list | grep super"
echo "    openclaw status | grep super_memory"
echo ""
echo "▶ Super Memory API must be running:"
echo "    super-memory-api &"
echo "    curl http://127.0.0.1:8765/health"
echo ""

# ── Optional restart ───────────────────────────────────────────────────────
read -rp "Restart OpenClaw gateway now? [y/N] " RESTART
if [[ "$RESTART" =~ ^[Yy]$ ]]; then
    echo "🔄 Restarting gateway..."
    openclaw gateway restart
fi

echo ""
echo "═══ Done ═══"
