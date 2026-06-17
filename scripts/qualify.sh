#!/usr/bin/env bash
set -euo pipefail

# ─── Super Memory Auto-Qualify ──────────────────────────────────────────────
# Production readiness qualification suite.
#
# Usage:
#   bash scripts/qualify.sh            # full qualification
#   bash scripts/qualify.sh --quick    # core checks only
#   bash scripts/qualify.sh --api      # also check API server
#
# ───────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PASS=0
FAIL=0
WARN=0
QUICK=false
CHECK_API=false

# Auto-detect Python from venv
if [ -f "$REPO_ROOT/.venv_test/bin/python3" ]; then
    PYTHON="$REPO_ROOT/.venv_test/bin/python3"
elif [ -f "$REPO_ROOT/.venv/bin/python3" ]; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
else
    PYTHON="python3"
fi
echo "🐍 Using Python: $PYTHON ($($PYTHON --version 2>&1))"

for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=true ;;
        --api) CHECK_API=true ;;
    esac
done

green()  { echo -e "\033[32m$1\033[0m"; }
red()    { echo -e "\033[31m$1\033[0m"; }
yellow() { echo -e "\033[33m$1\033[0m"; }

check() {
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
        green "  ✅ $label"
        PASS=$((PASS + 1))
    else
        red "  ❌ $label"
        FAIL=$((FAIL + 1))
    fi
}

warn_check() {
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
        green "  ✅ $label"
        PASS=$((PASS + 1))
    else
        yellow "  ⚠️  $label (optional)"
        WARN=$((WARN + 1))
    fi
}

echo ""
echo "═══ Super Memory Qualification ═══"
echo ""

# ── Python environment ─────────────────────────────────────────────────
echo "📦 Python Environment"
check "Python 3.11+"          $PYTHON -c "import sys; assert sys.version_info >= (3,11)"
check "super-memory package"  $PYTHON -c "import super_memory"
check "config model"          $PYTHON -c "from super_memory.models import SuperMemoryConfig; SuperMemoryConfig()"
echo ""

# ── Core modules ────────────────────────────────────────────────────────
echo "🧠 Core Modules"
check "storage.py"            $PYTHON -c "from super_memory.storage import SuperMemoryStore"
check "service.py"            $PYTHON -c "from super_memory.service import SuperMemoryService"
check "bridge.py"             $PYTHON -c "from super_memory.bridge import remember, recall, status"
check "api.py (FastAPI)"      $PYTHON -c "from super_memory.api import app"
check "cli.py (Typer)"        $PYTHON -c "from super_memory.cli import app"
echo ""

# ── Phase modules ───────────────────────────────────────────────────────
if [ "$QUICK" = false ]; then
    echo "🧩 Phase Modules"
    check "Ph1: sanitize"         $PYTHON -c "from super_memory.sanitize import sanitize_prompt"
    check "Ph3: intelligence"     $PYTHON -c "from super_memory.intelligence import conflicts, provenance, boundaries"
    check "Ph3: consolidation"    $PYTHON -c "from super_memory.consolidation import consolidate_real"
    check "Ph4: safe_flows"       $PYTHON -c "from super_memory.safe_flows import train, import_local"
    check "Ph4: extractors"       $PYTHON -c "from super_memory.extractors import extract_pdf, extract_docx"
    check "Ph5: phase5"           $PYTHON -c "from super_memory.phase5 import Phase5Plan"
    check "Ph6: cognitive"        $PYTHON -c "from super_memory.cognitive import working_memory_get"
    check "Ph7: graph"            $PYTHON -c "from super_memory.graph import recall"
    check "Ph7: lifecycle"        $PYTHON -c "from super_memory.lifecycle import review, cache, tier"
    check "Ph8: phase8"           $PYTHON -c "from super_memory.phase8 import diagnostics, supervised_runtime_smoke"
    check "MCP server"            $PYTHON -c "from super_memory.mcp_server import main"
    echo ""
fi

# ── DB adapters ─────────────────────────────────────────────────────────
echo "🗄️  Database Adapters"
check "SQLite adapter"        $PYTHON -c "from super_memory.db import SQLiteAdapter, get_adapter"
warn_check "PostgreSQL adapter (psycopg2)" $PYTHON -c "import psycopg2" 2>/dev/null || true
echo ""

# ── Plugin wrapper ──────────────────────────────────────────────────────
echo "🔌 OpenClaw Plugin Wrapper"
if [ -f "$REPO_ROOT/openclaw-plugin/super-memory/openclaw.plugin.json" ]; then
    TOOLS=$($PYTHON -c "import json; d=json.load(open('$REPO_ROOT/openclaw-plugin/super-memory/openclaw.plugin.json')); print(len(d.get('contracts',{}).get('tools',[])))")
    green "  ✅ openclaw.plugin.json ($TOOLS tools declared)"
    PASS=$((PASS + 1))
else
    red "  ❌ openclaw.plugin.json missing"
    FAIL=$((FAIL + 1))
fi

if [ -f "$REPO_ROOT/openclaw-plugin/super-memory/index.js" ]; then
    JS_LINES=$(wc -l < "$REPO_ROOT/openclaw-plugin/super-memory/index.js")
    green "  ✅ index.js ($JS_LINES lines)"
    PASS=$((PASS + 1))
else
    red "  ❌ index.js missing"
    FAIL=$((FAIL + 1))
fi
echo ""

# ── Deployment artifacts ────────────────────────────────────────────────
echo "🚀 Deployment"
check ".env.example"          test -f "$REPO_ROOT/.env.example"
check "systemd unit"          test -f "$REPO_ROOT/deploy/super-memory.service"
check "installer script"      test -f "$REPO_ROOT/scripts/install-openclaw-plugin.sh"
echo ""

# ── Test suite (quick) ──────────────────────────────────────────────────
echo "🧪 Test Suite"
cd "$REPO_ROOT"
if $PYTHON -m pytest tests/test_super_memory.py tests/test_promotion.py -x --tb=short -q >/tmp/sm-qualify-test.log 2>&1; then
    green "  ✅ Core tests pass"
    PASS=$((PASS + 1))
else
    red "  ❌ Core tests failed"
    FAIL=$((FAIL + 1))
fi
echo ""

# ── API health check (optional) ─────────────────────────────────────────
if [ "$CHECK_API" = true ]; then
    echo "🌐 API Server"
    if curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then
        green "  ✅ API healthy (127.0.0.1:8765)"
        PASS=$((PASS + 1))
    else
        yellow "  ⚠️  API not running (start: super-memory-api &)"
        WARN=$((WARN + 1))
    fi
    echo ""
fi

# ── Summary ─────────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: $(green "$PASS passed") / $(red "$FAIL failed") / $(yellow "$WARN warnings")"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $FAIL -gt 0 ]; then
    echo ""
    red "❌ QUALIFICATION FAILED — $FAIL checks did not pass"
    exit 1
else
    echo ""
    green "✅ QUALIFICATION PASSED"
    exit 0
fi
