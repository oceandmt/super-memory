#!/usr/bin/env bash
# Upload a reviewed artifact and invoke the guarded remote upgrade.
# All network and remote mutation require --execute.
set -euo pipefail

LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYBIN="${PYBIN:-$LOCAL_ROOT/.venv/bin/python}"
VPS_HOST="${VPS_HOST:-}"
VPS_PORT="${VPS_PORT:-22}"
REMOTE_STAGING_ROOT="${REMOTE_STAGING_ROOT:-/tmp/super-memory-releases}"
REMOTE_CONFIG="${REMOTE_CONFIG:-}"
REMOTE_INSTALL_ROOT="${REMOTE_INSTALL_ROOT:-/opt/super-memory}"
REMOTE_PYBIN="${REMOTE_PYBIN:-$REMOTE_INSTALL_ROOT/.venv/bin/python}"
SERVICE="${SUPER_MEMORY_SERVICE:-super-memory.service}"
HEALTH_URL="${SUPER_MEMORY_HEALTH_URL:-http://127.0.0.1:8765/health}"
SMOKE_URL="${SUPER_MEMORY_SMOKE_URL:-$HEALTH_URL}"
MIN_CASES="${SUPER_MEMORY_MIN_RECALL_CASES:-5}"
RELEASE_ID="${SUPER_MEMORY_RELEASE_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
EXECUTE=0

usage() {
  cat <<'EOF'
Usage: deploy_verify_vps.sh [--execute] --host USER@HOST --remote-config PATH [options]

Without --execute this performs no ssh/scp/network or remote mutation. The
remote rollout is delegated to deploy-vps.sh, which requires a verified backup,
copy-based migration pass, evidence recall gate, rollback manifest, ready=true,
and bounded smoke success.

Options:
  --execute                 upload and execute remotely
  --host USER@HOST          SSH destination
  --port PORT               SSH port
  --remote-config PATH      existing live config on VPS
  --remote-install-root DIR immutable releases/current/backups root
  --remote-python PATH      existing remote Python (no install)
  --staging-root DIR        remote temporary artifact root
  --service NAME            remote systemd service
  --health-url URL          remote-local readiness URL
  --smoke-url URL           remote-local bounded smoke URL
  --release-id ID           immutable release identifier
  --min-cases N             minimum oracle cases
EOF
}

while (($#)); do
  case "$1" in
    --execute) EXECUTE=1; shift ;;
    --host) VPS_HOST="${2:?missing --host value}"; shift 2 ;;
    --port) VPS_PORT="${2:?missing --port value}"; shift 2 ;;
    --remote-config) REMOTE_CONFIG="${2:?missing --remote-config value}"; shift 2 ;;
    --remote-install-root) REMOTE_INSTALL_ROOT="${2:?missing value}"; shift 2 ;;
    --remote-python) REMOTE_PYBIN="${2:?missing value}"; shift 2 ;;
    --staging-root) REMOTE_STAGING_ROOT="${2:?missing value}"; shift 2 ;;
    --service) SERVICE="${2:?missing value}"; shift 2 ;;
    --health-url) HEALTH_URL="${2:?missing value}"; shift 2 ;;
    --smoke-url) SMOKE_URL="${2:?missing value}"; shift 2 ;;
    --release-id) RELEASE_ID="${2:?missing value}"; shift 2 ;;
    --min-cases) MIN_CASES="${2:?missing value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

remote_stage="$REMOTE_STAGING_ROOT/$RELEASE_ID"
cat <<EOF
[deploy_verify_vps] mode=$([[ "$EXECUTE" == 1 ]] && echo execute || echo dry-run)
[deploy_verify_vps] destination=${VPS_HOST:-<required>}:$remote_stage
[deploy_verify_vps] no direct main/master push or any git push is performed
[deploy_verify_vps] remote execution remains fail-closed behind deploy-vps.sh --execute
EOF
if [[ "$EXECUTE" != 1 ]]; then
  echo "[deploy_verify_vps] DRY RUN ONLY; pass --execute after reviewing the destination"
  exit 0
fi

[[ -x "$PYBIN" ]] || { echo "local Python not executable: $PYBIN" >&2; exit 2; }
[[ -n "$VPS_HOST" && "$VPS_HOST" != *'<'* ]] || { echo "--host is required and placeholders are refused" >&2; exit 2; }
[[ "$VPS_PORT" =~ ^[1-9][0-9]{0,4}$ ]] || { echo "invalid SSH port" >&2; exit 2; }
[[ -n "$REMOTE_CONFIG" && "$REMOTE_CONFIG" = /* ]] || { echo "--remote-config must be an absolute path" >&2; exit 2; }
[[ "$RELEASE_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "unsafe release id" >&2; exit 2; }
[[ "$MIN_CASES" =~ ^[1-9][0-9]*$ ]] || { echo "--min-cases must be positive" >&2; exit 2; }
command -v ssh >/dev/null || { echo "ssh is required" >&2; exit 2; }
command -v tar >/dev/null || { echo "tar is required" >&2; exit 2; }

"$PYBIN" -m compileall -q "$LOCAL_ROOT/super_memory" "$LOCAL_ROOT/scripts/super_memory_release_gate.py"
# Oracle files are uploaded as evaluation data only. The gate never indexes or seeds them.
printf -v remote_stage_q '%q' "$remote_stage"
ssh -p "$VPS_PORT" "$VPS_HOST" "test ! -e $remote_stage_q && mkdir -p $remote_stage_q"
tar -C "$LOCAL_ROOT" \
  --exclude=.git --exclude=.venv --exclude='__pycache__' --exclude='.release-backups' \
  -cf - . | ssh -p "$VPS_PORT" "$VPS_HOST" "tar -C $remote_stage_q -xf -"

remote_cases="$remote_stage/tests/recall_cases"
printf -v cmd '%q ' \
  "$remote_stage/scripts/deploy-vps.sh" --execute \
  --config "$REMOTE_CONFIG" \
  --cases "$remote_cases" \
  --install-root "$REMOTE_INSTALL_ROOT" \
  --python "$REMOTE_PYBIN" \
  --service "$SERVICE" \
  --health-url "$HEALTH_URL" \
  --smoke-url "$SMOKE_URL" \
  --release-id "$RELEASE_ID" \
  --min-cases "$MIN_CASES"
ssh -p "$VPS_PORT" "$VPS_HOST" "$cmd"

echo "[deploy_verify_vps] SUPER_MEMORY_DEPLOY_VERIFY_OK release=$RELEASE_ID"
