#!/usr/bin/env bash
set -euo pipefail

# ─── Super Memory Batch Test Runner ─────────────────────────────────────────
# Runs the full 136-test suite in parallel batches to avoid OOM.
# Usage:
#   bash scripts/batch_test.sh            # all batches
#   bash scripts/batch_test.sh --quick    # core only (fast)
#   bash scripts/batch_test.sh --fail-fast # stop at first failure
#
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

QUICK=false
FAIL_FAST=""
for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=true ;;
        --fail-fast) FAIL_FAST="-x" ;;
    esac
done

# Auto-detect Python from venv
if [ -f ".venv_test/bin/python3" ]; then
    PYTHON=".venv_test/bin/python3"
elif [ -f ".venv/bin/python3" ]; then
    PYTHON=".venv/bin/python3"
else
    PYTHON="python3"
fi

PASS=0
FAIL=0
TOTAL=0

green()  { echo -e "\033[32m$1\033[0m"; }
red()    { echo -e "\033[31m$1\033[0m"; }

run_batch() {
    local label="$1"; shift
    echo ""
    echo "═══ $label ═══"
    if $PYTHON -m pytest "$@" $FAIL_FAST --tb=short -q 2>/dev/null; then
        green "  ✅ $label"
        PASS=$((PASS + 1))
    else
        local rc=$?
        red "  ❌ $label (exit $rc)"
        FAIL=$((FAIL + 1))
        if [ -n "$FAIL_FAST" ]; then
            exit $rc
        fi
    fi
    TOTAL=$((TOTAL + 1))
}

echo "🧪 Super Memory Batch Test Runner"
echo "   Python: $($PYTHON --version 2>&1)"

if [ "$QUICK" = true ]; then
    echo "   Mode: quick (core only)"
    run_batch "Core + Quality" \
        tests/test_super_memory.py tests/test_promotion.py \
        tests/test_p0_p5_quality.py tests/test_p0_p5_edge_cases.py
else
    echo "   Mode: full (all batches)"

    # Batch 0: Pre-flight
    echo ""
    echo "── Pre-flight ──"
    $PYTHON scripts/check_sql_safety.py
    green "  ✅ SQL safety"

    # Batch 1: Core + Quality (49 tests)
    run_batch "Batch 1: Core + Quality" \
        tests/test_super_memory.py tests/test_promotion.py \
        tests/test_p0_p5_quality.py tests/test_p0_p5_edge_cases.py

    # Batch 2: Phases 1-5 (16 tests)
    run_batch "Batch 2: Phases 1-5" \
        tests/test_phase1_tools.py tests/test_phase11_sanitize.py \
        tests/test_phases_2_4.py tests/test_phase5_sandbox.py \
        tests/test_property_based.py

    # Batch 3: Cognitive + Graph (6 tests)
    run_batch "Batch 3: Cognitive + Graph" \
        tests/test_phase6_cognitive.py tests/test_phase7_layer4.py

    # Batch 4: Contract + Live Readiness (11 tests)
    run_batch "Batch 4: Contract + Live Readiness" \
        tests/test_phase8_contracts.py tests/test_phase8_live_readiness.py

    # Batch 5: API + MCP + Extended (30 tests)
    run_batch "Batch 5: API + MCP + Extended" \
        tests/test_api.py tests/test_mcp_server.py tests/test_p2_extended.py \
        tests/test_memory_core_compat.py tests/test_multi_agent_graph.py \
        tests/test_openclaw_plugin_guardrails.py \
        tests/test_openclaw_plugin_memory_slot_contract.py

    # Batch 6: Heavy (6 tests)
    run_batch "Batch 6: Heavy" \
        tests/test_p4_graph_v2.py tests/test_performance_smoke.py \
        tests/test_tool_catalog_snapshot.py tests/test_grpc_stub.py
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: $(green "$PASS passed") / $(red "$FAIL failed") batches"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $FAIL -gt 0 ]; then
    exit 1
fi
