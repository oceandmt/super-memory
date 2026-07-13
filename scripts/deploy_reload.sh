#!/usr/bin/env bash
# E11: post-deploy reload hook for Super Memory.
#
# Root-cause lesson (2026-07-13): code edits to super_memory/*.py stay INERT
# until the long-lived systemd user service `super-memory-api` is restarted.
# Restarting the OpenClaw gateway only respawns the MCP stdio subprocess, NOT
# this daemon (the real data path via apiBaseUrl http://127.0.0.1:8765).
#
# Run this after ANY change to super_memory/*.py or super-memory.yaml.
set -euo pipefail

SERVICE="super-memory-api.service"
HEALTH_URL="http://127.0.0.1:8765/health"
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[deploy_reload] byte-compiling package to catch syntax errors first..."
PYBIN="/home/oceandmt/.openclaw/venvs/super-memory-cli/bin/python"
"$PYBIN" -m compileall -q "$PKG_DIR/super_memory" || {
  echo "[deploy_reload] FAILED: syntax error in package, NOT restarting." >&2
  exit 1
}

echo "[deploy_reload] restarting $SERVICE ..."
systemctl --user restart "$SERVICE"

echo "[deploy_reload] waiting for health ..."
for i in $(seq 1 15); do
  sleep 1
  if curl -s -m 3 "$HEALTH_URL" 2>/dev/null | grep -q '"ok":true'; then
    echo "[deploy_reload] OK: service healthy after ${i}s"
    systemctl --user show "$SERVICE" -p MainPID -p SubState -p NRestarts 2>/dev/null
    exit 0
  fi
done

echo "[deploy_reload] WARNING: health check did not pass within 15s" >&2
systemctl --user status "$SERVICE" --no-pager 2>/dev/null | head -15 || true
exit 2
