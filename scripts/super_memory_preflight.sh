#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .venv/bin/python3 ]; then
  PY=".venv/bin/python3"
else
  PY="python3"
fi

printf '%s\n' '=== COMPILE ==='
$PY -m py_compile super_memory/*.py tests/test_p0_p5_quality.py
printf '%s\n' 'COMPILE_OK'

printf '%s\n' '=== SQL SAFETY ==='
$PY scripts/check_sql_safety.py

printf '%s\n' '=== TOOL CONTRACTS ==='
$PY scripts/check_tool_contracts.py

printf '%s\n' '=== PYTEST QUALITY ==='
$PY -m pytest tests/test_p0_p5_quality.py -q

if [ -f tests/test_p0_p5_edge_cases.py ]; then
  printf '%s\n' '=== PYTEST EDGE CASES ==='
  $PY -m pytest tests/test_p0_p5_edge_cases.py -q
fi

printf '%s\n' 'SUPER_MEMORY_PREFLIGHT_OK'
