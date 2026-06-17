#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# Super Memory — VPS One-Shot Deploy Script
# Repo: https://github.com/oceandmt/super-memory
#
# Usage (on VPS):
#   curl -sL https://raw.githubusercontent.com/oceandmt/super-memory/master/scripts/deploy-vps.sh | bash
#
# Or manually:
#   git clone https://github.com/oceandmt/super-memory.git /tmp/super-memory
#   cd /tmp/super-memory && bash scripts/deploy-vps.sh
# ═══════════════════════════════════════════════════════════════════════════════

GREEN='\033[32m'
RED='\033[31m'
YELLOW='\033[33m'
NC='\033[0m'

say()  { echo -e "${GREEN}▶${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC}  $1"; }
die()  { echo -e "${RED}✘${NC}  $1"; exit 1; }

# ── Auto-detect repo root ───────────────────────────────────────────────────
if [ -f "$(dirname "$0")/../pyproject.toml" ]; then
    REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
elif [ -f "./pyproject.toml" ]; then
    REPO_ROOT="$(pwd)"
else
    die "pyproject.toml not found. Run from super-memory repo root."
fi

WORKSPACE_ROOT="${SUPER_MEMORY_WORKSPACE_ROOT:-$HOME/.openclaw/workspace}"
INSTALL_DIR="/opt/super-memory"

echo ""
echo "══════════════════════════════════════════════"
echo "   Super Memory — VPS Deploy"
echo "   $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════"
echo ""

# ── Step 0: Check pre-reqs ──────────────────────────────────────────────────
say "Checking prerequisites..."
command -v python3 &>/dev/null || die "python3 not found"
command -v pip &>/dev/null || die "pip not found"
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
[ "$(echo "$PY_VER" | cut -d. -f1)" -ge 3 ] && [ "$(echo "$PY_VER" | cut -d. -f2)" -ge 11 ] || die "Python 3.11+ required, found $PY_VER"
command -v systemctl &>/dev/null || warn "systemctl not found — skipping systemd install"
echo "  ✓ Python $PY_VER"
echo ""

# ── Step 1: Copy to install dir ─────────────────────────────────────────────
say "Installing to $INSTALL_DIR..."
sudo mkdir -p "$INSTALL_DIR"
sudo cp -r "$REPO_ROOT"/* "$INSTALL_DIR/"
sudo chown -R "$(whoami):$(whoami)" "$INSTALL_DIR"
echo "  ✓ Copied"
echo ""

# ── Step 2: Create venv + install ───────────────────────────────────────────
say "Setting up Python venv..."
cd "$INSTALL_DIR"
python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -e '.[dev]'
echo "  ✓ Installed"
echo ""

# ── Step 3: Configure .env ──────────────────────────────────────────────────
say "Configuring environment..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    # Auto-fill workspace root
    sed -i "s|SUPER_MEMORY_WORKSPACE_ROOT=.*|SUPER_MEMORY_WORKSPACE_ROOT=$WORKSPACE_ROOT|" "$INSTALL_DIR/.env"
fi
echo "  ✓ .env configured (workspace_root=$WORKSPACE_ROOT)"
echo ""

# ── Step 4: Install systemd service ─────────────────────────────────────────
if command -v systemctl &>/dev/null; then
    say "Installing systemd service..."
    # Update paths in unit file to match INSTALL_DIR
    sed "s|/home/oceandmt/.openclaw/workspace/projects/super-memory-github|$INSTALL_DIR|g" \
        "$INSTALL_DIR/deploy/super-memory.service" | \
    sed "s|/home/oceandmt/Documents/super-memory-github|$INSTALL_DIR|g" | \
    sudo tee /etc/systemd/system/super-memory.service > /dev/null

    sudo systemctl daemon-reload
    sudo systemctl enable super-memory
    sudo systemctl restart super-memory
    sleep 2
    if sudo systemctl is-active --quiet super-memory; then
        echo "  ✓ Service running"
    else
        warn "Service failed to start — check: sudo journalctl -u super-memory -n 30"
    fi
    echo ""
fi

# ── Step 5: Verify API health ───────────────────────────────────────────────
say "Verifying API health..."
sleep 1
if curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then
    echo "  ✓ API healthy at http://127.0.0.1:8765"
    curl -s http://127.0.0.1:8765/health | python3 -m json.tool 2>/dev/null || true
else
    warn "API health check failed — trying manual start..."
    cd "$INSTALL_DIR"
    . .venv/bin/activate
    nohup super-memory-api > /tmp/super-memory.log 2>&1 &
    sleep 2
    if curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then
        echo "  ✓ API started manually"
    else
        warn "API still not reachable — check /tmp/super-memory.log"
    fi
fi
echo ""

# ── Step 6: Install OpenClaw plugin ─────────────────────────────────────────
if command -v openclaw &>/dev/null; then
    say "Installing OpenClaw plugin..."
    bash "$INSTALL_DIR/scripts/install-openclaw-plugin.sh"
    echo ""
else
    warn "openclaw CLI not found on this machine — skipping plugin install"
    warn "Run this on the machine where OpenClaw Gateway is running"
    echo ""
fi

# ── Step 7: Run qualification ───────────────────────────────────────────────
say "Running auto-qualify..."
bash "$INSTALL_DIR/scripts/qualify.sh" || warn "Some qualification checks failed — review above"
echo ""

# ── Done ────────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════"
echo "  ✅ DEPLOY COMPLETE"
echo "══════════════════════════════════════════════"
echo ""
echo "  Install dir:  $INSTALL_DIR"
echo "  API:          http://127.0.0.1:8765"
echo "  Health:       http://127.0.0.1:8765/health"
echo "  Docs:         http://127.0.0.1:8765/docs"
echo "  Service:      sudo systemctl status super-memory"
echo "  Logs:         sudo journalctl -u super-memory -f"
echo ""
echo "  Plugin (on OpenClaw Gateway host):"
echo "    bash $INSTALL_DIR/scripts/install-openclaw-plugin.sh"
echo "    openclaw gateway restart"
echo ""

# ── Key reminder for Luffy integration ──────────────────────────────────────
echo "===== LUFFY INTEGRATION ====="
echo ""
echo "Super Memory is now running as a systemd service on this VPS."
echo "Tools are exposed via MCP (stdio) and REST (127.0.0.1:8765)."
echo ""
echo "For OpenClaw Luffy to use super-memory tools:"
echo ""
echo "  1. Run the plugin installer on the OpenClaw Gateway host:"
echo "     bash $INSTALL_DIR/scripts/install-openclaw-plugin.sh"
echo ""
echo "  2. Choose activation mode when prompted:"
echo "     MODE A (recommended): additive tools alongside existing memory"
echo "     MODE B: exclusive memory slot (replaces memory-core)"
echo ""
echo "  3. Restart gateway:"
echo "     openclaw gateway restart"
echo ""
echo "  4. Verify:"
echo "     openclaw plugins list | grep super"
echo "     openclaw status | grep super_memory"
echo ""
