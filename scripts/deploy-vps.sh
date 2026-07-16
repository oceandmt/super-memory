#!/usr/bin/env bash
# Guarded in-place VPS upgrade from a reviewed local checkout/artifact.
# This script never clones, installs dependencies, commits, or pushes branches.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="${SUPER_MEMORY_INSTALL_ROOT:-/opt/super-memory}"
CURRENT_LINK="${SUPER_MEMORY_CURRENT_LINK:-$INSTALL_ROOT/current}"
RELEASES_DIR="${SUPER_MEMORY_RELEASES_DIR:-$INSTALL_ROOT/releases}"
BACKUP_DIR="${SUPER_MEMORY_BACKUP_DIR:-$INSTALL_ROOT/backups}"
PYBIN="${PYBIN:-$INSTALL_ROOT/.venv/bin/python}"
CONFIG="${SUPER_MEMORY_CONFIG:-}"
CASES="${SUPER_MEMORY_RECALL_CASES:-}"
SERVICE="${SUPER_MEMORY_SERVICE:-super-memory.service}"
HEALTH_URL="${SUPER_MEMORY_HEALTH_URL:-http://127.0.0.1:8765/health}"
SMOKE_URL="${SUPER_MEMORY_SMOKE_URL:-$HEALTH_URL}"
MIN_CASES="${SUPER_MEMORY_MIN_RECALL_CASES:-5}"
RELEASE_ID="${SUPER_MEMORY_RELEASE_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
EXECUTE=0

usage() {
  cat <<'EOF'
Usage: deploy-vps.sh [--execute] --config PATH --cases DIR [options]

This is an upgrade tool, not an initial provisioner. Without --execute it only
prints a plan. Execution requires an existing current release and database so a
verified rollback can be prepared before cutover.

Options:
  --execute              perform the guarded upgrade
  --config PATH          live Super Memory config
  --cases DIR            independent recall oracle
  --install-root DIR     release/current/backups root
  --python PATH          pre-existing Python environment (no installs occur)
  --service NAME         systemd service name
  --health-url URL       endpoint whose JSON must contain ready=true
  --smoke-url URL        bounded smoke endpoint
  --release-id ID        immutable release directory name
  --min-cases N          minimum recall cases (default: 5)
EOF
}

while (($#)); do
  case "$1" in
    --execute) EXECUTE=1; shift ;;
    --config) CONFIG="${2:?missing --config value}"; shift 2 ;;
    --cases) CASES="${2:?missing --cases value}"; shift 2 ;;
    --install-root)
      INSTALL_ROOT="${2:?missing --install-root value}"
      CURRENT_LINK="$INSTALL_ROOT/current"; RELEASES_DIR="$INSTALL_ROOT/releases"; BACKUP_DIR="$INSTALL_ROOT/backups"
      shift 2 ;;
    --python) PYBIN="${2:?missing --python value}"; shift 2 ;;
    --service) SERVICE="${2:?missing --service value}"; shift 2 ;;
    --health-url) HEALTH_URL="${2:?missing --health-url value}"; shift 2 ;;
    --smoke-url) SMOKE_URL="${2:?missing --smoke-url value}"; shift 2 ;;
    --release-id) RELEASE_ID="${2:?missing --release-id value}"; shift 2 ;;
    --min-cases) MIN_CASES="${2:?missing --min-cases value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

new_release="$RELEASES_DIR/$RELEASE_ID"
cat <<EOF
[deploy-vps] mode=$([[ "$EXECUTE" == 1 ]] && echo execute || echo dry-run)
[deploy-vps] source=$REPO_ROOT new_release=$new_release current=$CURRENT_LINK
[deploy-vps] guarded order: compile -> migration-copy -> recall evidence -> verified backup -> immutable copy -> cutover -> restart -> ready=true -> smoke
[deploy-vps] no package install, git commit, or git push is performed
EOF
if [[ "$EXECUTE" != 1 ]]; then
  echo "[deploy-vps] DRY RUN ONLY; pass --execute with --config and --cases to mutate"
  exit 0
fi

[[ -x "$PYBIN" ]] || { echo "pre-existing Python is required: $PYBIN" >&2; exit 2; }
[[ -n "$CONFIG" && -f "$CONFIG" ]] || { echo "--config must name an existing live config" >&2; exit 2; }
[[ -n "$CASES" && -d "$CASES" ]] || { echo "--cases must name an independent oracle directory" >&2; exit 2; }
[[ "$MIN_CASES" =~ ^[1-9][0-9]*$ ]] || { echo "--min-cases must be positive" >&2; exit 2; }
[[ "$RELEASE_ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "unsafe release id" >&2; exit 2; }
[[ -L "$CURRENT_LINK" ]] || { echo "existing current release symlink required for rollback: $CURRENT_LINK" >&2; exit 2; }
previous_release="$(readlink -f "$CURRENT_LINK")"
[[ -d "$previous_release" ]] || { echo "previous release missing: $previous_release" >&2; exit 2; }
[[ ! -e "$new_release" ]] || { echo "immutable release already exists: $new_release" >&2; exit 2; }
command -v systemctl >/dev/null || { echo "systemctl is required" >&2; exit 2; }

source_gate="$REPO_ROOT/scripts/super_memory_release_gate.py"
"$PYBIN" -m compileall -q "$REPO_ROOT/super_memory" "$source_gate"
"$PYBIN" "$source_gate" migration-dry-run --config "$CONFIG"
"$PYBIN" "$source_gate" recall --config "$CONFIG" --cases "$CASES" --min-cases "$MIN_CASES"

mkdir -p "$BACKUP_DIR" "$RELEASES_DIR"
backup="$BACKUP_DIR/super-memory-$RELEASE_ID.sqlite3"
manifest="$BACKUP_DIR/super-memory-$RELEASE_ID.rollback.json"
installed_gate="$new_release/scripts/super_memory_release_gate.py"
printf -v rollback_command '%q %q rollback --manifest %q --execute' "$PYBIN" "$installed_gate" "$manifest"
"$PYBIN" "$source_gate" backup \
  --config "$CONFIG" \
  --output "$backup" \
  --manifest "$manifest" \
  --current-link "$CURRENT_LINK" \
  --previous-release "$previous_release" \
  --new-release "$new_release" \
  --service "$SERVICE" \
  --rollback-command "$rollback_command"
"$PYBIN" "$source_gate" verify-backup --manifest "$manifest"

rollback_required=0
rollback_on_error() {
  status=$?
  trap - ERR
  if [[ "$rollback_required" == 1 ]]; then
    echo "[deploy-vps] rollout failed; executing verified rollback" >&2
    gate="$source_gate"
    [[ -f "$installed_gate" ]] && gate="$installed_gate"
    "$PYBIN" "$gate" rollback --manifest "$manifest" --execute || true
    systemctl restart "$SERVICE" || true
  fi
  exit "$status"
}
trap rollback_on_error ERR
rollback_required=1

mkdir "$new_release"
# Copy the reviewed artifact without VCS state, caches, local venvs, or release backups.
tar -C "$REPO_ROOT" \
  --exclude=.git --exclude=.venv --exclude='__pycache__' --exclude='.release-backups' \
  -cf - . | tar -C "$new_release" -xf -
"$PYBIN" -m compileall -q "$new_release/super_memory" "$installed_gate"
ln -s "$new_release" "$CURRENT_LINK.next-$RELEASE_ID"
mv -Tf "$CURRENT_LINK.next-$RELEASE_ID" "$CURRENT_LINK"
systemctl restart "$SERVICE"
"$PYBIN" "$installed_gate" readiness --url "$HEALTH_URL" --attempts 20 --timeout 2 --interval 1
"$PYBIN" "$installed_gate" smoke --url "$SMOKE_URL" --timeout 3 --require-json-key ready
rollback_required=0
trap - ERR

echo "[deploy-vps] RELEASE_OK release=$new_release manifest=$manifest"
echo "[deploy-vps] rollback: $rollback_command && systemctl restart $(printf %q "$SERVICE")"
