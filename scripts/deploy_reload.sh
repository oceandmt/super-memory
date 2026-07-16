#!/usr/bin/env bash
# Safe local reload gate. Dry-run by default; --execute is required for mutation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYBIN="${PYBIN:-$ROOT/.venv/bin/python}"
GATE="$ROOT/scripts/super_memory_release_gate.py"
SERVICE="${SUPER_MEMORY_SERVICE:-super-memory-api.service}"
HEALTH_URL="${SUPER_MEMORY_HEALTH_URL:-http://127.0.0.1:8765/health}"
SMOKE_URL="${SUPER_MEMORY_SMOKE_URL:-$HEALTH_URL}"
BACKUP_DIR="${SUPER_MEMORY_BACKUP_DIR:-$ROOT/.release-backups}"
CONFIG="${SUPER_MEMORY_CONFIG:-}"
CASES="${SUPER_MEMORY_RECALL_CASES:-}"
MIN_CASES="${SUPER_MEMORY_MIN_RECALL_CASES:-5}"
EXECUTE=0

usage() {
  cat <<'EOF'
Usage: deploy_reload.sh [--execute] --config PATH --cases DIR [options]

Without --execute this only prints the guarded rollout plan and performs no
backup, migration, network, service, or database operation.

Options:
  --execute            perform the guarded reload
  --config PATH        live Super Memory config (required for execution)
  --cases DIR          independent recall oracle directory (required)
  --backup-dir DIR     immutable backup/manifest destination
  --service NAME       systemd user service
  --health-url URL     endpoint whose JSON must contain ready=true
  --smoke-url URL      bounded post-readiness smoke endpoint
  --min-cases N        minimum independent oracle cases (default: 5)
EOF
}

while (($#)); do
  case "$1" in
    --execute) EXECUTE=1; shift ;;
    --config) CONFIG="${2:?missing --config value}"; shift 2 ;;
    --cases) CASES="${2:?missing --cases value}"; shift 2 ;;
    --backup-dir) BACKUP_DIR="${2:?missing --backup-dir value}"; shift 2 ;;
    --service) SERVICE="${2:?missing --service value}"; shift 2 ;;
    --health-url) HEALTH_URL="${2:?missing --health-url value}"; shift 2 ;;
    --smoke-url) SMOKE_URL="${2:?missing --smoke-url value}"; shift 2 ;;
    --min-cases) MIN_CASES="${2:?missing --min-cases value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

cat <<EOF
[deploy_reload] mode=$([[ "$EXECUTE" == 1 ]] && echo execute || echo dry-run)
[deploy_reload] guarded order: compile -> migration-copy -> recall evidence -> verified backup -> restart -> ready=true -> bounded smoke
[deploy_reload] service=$SERVICE health=$HEALTH_URL
[deploy_reload] this script does not commit or push git branches
EOF

if [[ "$EXECUTE" != 1 ]]; then
  echo "[deploy_reload] DRY RUN ONLY; pass --execute with --config and --cases to mutate"
  exit 0
fi

[[ -x "$PYBIN" ]] || { echo "Python not executable: $PYBIN" >&2; exit 2; }
[[ -f "$GATE" ]] || { echo "release helper missing: $GATE" >&2; exit 2; }
[[ -n "$CONFIG" && -f "$CONFIG" ]] || { echo "--config must name an existing file" >&2; exit 2; }
[[ -n "$CASES" && -d "$CASES" ]] || { echo "--cases must name an independent oracle directory" >&2; exit 2; }
[[ "$MIN_CASES" =~ ^[1-9][0-9]*$ ]] || { echo "--min-cases must be positive" >&2; exit 2; }
command -v systemctl >/dev/null || { echo "systemctl is required" >&2; exit 2; }

"$PYBIN" -m compileall -q "$ROOT/super_memory" "$GATE"
"$PYBIN" "$GATE" migration-dry-run --config "$CONFIG"
"$PYBIN" "$GATE" recall --config "$CONFIG" --cases "$CASES" --min-cases "$MIN_CASES"

release_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$BACKUP_DIR"
backup="$BACKUP_DIR/super-memory-$release_id.sqlite3"
manifest="$BACKUP_DIR/super-memory-$release_id.rollback.json"
printf -v rollback_command '%q %q rollback --manifest %q --execute' "$PYBIN" "$GATE" "$manifest"
"$PYBIN" "$GATE" backup \
  --config "$CONFIG" \
  --output "$backup" \
  --manifest "$manifest" \
  --service "$SERVICE" \
  --rollback-command "$rollback_command"
"$PYBIN" "$GATE" verify-backup --manifest "$manifest"

rollback_required=0
rollback_on_error() {
  status=$?
  trap - ERR
  if [[ "$rollback_required" == 1 ]]; then
    echo "[deploy_reload] rollout failed; restoring verified database backup" >&2
    "$PYBIN" "$GATE" rollback --manifest "$manifest" --execute || true
    systemctl --user restart "$SERVICE" || true
  fi
  exit "$status"
}
trap rollback_on_error ERR

rollback_required=1
systemctl --user restart "$SERVICE"
"$PYBIN" "$GATE" readiness --url "$HEALTH_URL" --attempts 15 --timeout 2 --interval 1
"$PYBIN" "$GATE" smoke --url "$SMOKE_URL" --timeout 3 --require-json-key ready
rollback_required=0
trap - ERR

echo "[deploy_reload] RELEASE_OK manifest=$manifest"
echo "[deploy_reload] rollback: $rollback_command && systemctl --user restart $(printf %q "$SERVICE")"
