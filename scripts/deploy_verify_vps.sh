#!/usr/bin/env bash
set -euo pipefail

VPS_HOST="${VPS_HOST:-<VPS_USER>@<VPS_HOST>}"
VPS_PORT="${VPS_PORT:-<VPS_PORT>}"
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_ROOT="${REMOTE_ROOT:-${REMOTE_ROOT}}"

cd "$LOCAL_ROOT"

printf '%s\n' '=== LOCAL PREFLIGHT ==='
bash scripts/super_memory_preflight.sh

printf '%s\n' '=== DEPLOY FILES ==='
ssh -p "$VPS_PORT" "$VPS_HOST" "mkdir -p '$REMOTE_ROOT/super_memory' '$REMOTE_ROOT/tests' '$REMOTE_ROOT/scripts'"
scp -P "$VPS_PORT" super_memory/*.py super_memory/schema.sql "$VPS_HOST:$REMOTE_ROOT/super_memory/"
scp -P "$VPS_PORT" tests/test_p0_p5_quality.py tests/test_p0_p5_edge_cases.py "$VPS_HOST:$REMOTE_ROOT/tests/"
scp -P "$VPS_PORT" scripts/check_sql_safety.py scripts/check_tool_contracts.py scripts/super_memory_preflight.sh "$VPS_HOST:$REMOTE_ROOT/scripts/"
scp -P "$VPS_PORT" openclaw-plugin/super-memory/openclaw.plugin.json "$VPS_HOST:$REMOTE_ROOT/openclaw.plugin.json"

printf '%s\n' '=== REMOTE COMPILE + PREFLIGHT ==='
ssh -p "$VPS_PORT" "$VPS_HOST" "cd '$REMOTE_ROOT' && ${REMOTE_ROOT}/.venv/bin/python3 -m py_compile super_memory/*.py tests/test_p0_p5_quality.py tests/test_p0_p5_edge_cases.py && ${REMOTE_ROOT}/.venv/bin/python3 scripts/check_sql_safety.py && ${REMOTE_ROOT}/.venv/bin/python3 scripts/check_tool_contracts.py && ${REMOTE_ROOT}/.venv/bin/python3 -m pytest tests/test_p0_p5_quality.py tests/test_p0_p5_edge_cases.py -q"

printf '%s\n' '=== RESTART SERVICE ==='
ssh -p "$VPS_PORT" "$VPS_HOST" "systemctl restart super-memory-api.service && sleep 2 && systemctl is-active super-memory-api.service"

printf '%s\n' '=== INTEGRATION CHECKS ==='
ssh -p "$VPS_PORT" "$VPS_HOST" "cd '$REMOTE_ROOT' && ${REMOTE_ROOT}/.venv/bin/python3 /tmp/test_quick_wins.py && ${REMOTE_ROOT}/.venv/bin/python3 /tmp/test_p0_p5_vps.py"

printf '%s\n' 'SUPER_MEMORY_DEPLOY_VERIFY_OK'
