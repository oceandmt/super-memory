#!/usr/bin/env python3
"""Fail-closed Super Memory release checks.

This helper is deliberately standard-library-only. It performs read-only recall
and migration checks by default. Mutating operations require an explicit
subcommand, and rollback additionally requires ``--execute``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _emit(payload: dict[str, Any], *, plain: str | None = None) -> int:
    if plain is not None:
        print(plain)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_evidence(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "path": str(path), "error": "database_missing"}
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as conn:
            integrity = [str(row[0]) for row in conn.execute("PRAGMA integrity_check").fetchall()]
            tables = [
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        return {
            "ok": integrity == ["ok"],
            "path": str(path),
            "integrity_check": integrity,
            "table_count": len(tables),
            "tables": tables,
            "page_count": page_count,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    except Exception as exc:
        return {"ok": False, "path": str(path), "error": f"{type(exc).__name__}: {exc}"}


def _config_db(config: str | None) -> tuple[Any, Path]:
    from super_memory.doctor import _database_path

    return _database_path(config)


def command_db_path(args: argparse.Namespace) -> int:
    _, path = _config_db(args.config)
    return _emit({"ok": True, "sqlite_path": str(path)}, plain=str(path))


def command_isolation(args: argparse.Namespace) -> int:
    from super_memory.doctor import test_isolation_status

    return _emit(test_isolation_status(args.config))


def command_migration(args: argparse.Namespace) -> int:
    from super_memory.doctor import migration_status

    result = migration_status(args.config, dry_run=True)
    result["gate"] = "copy_based_migration_dry_run"
    return _emit(result)


def command_recall(args: argparse.Namespace) -> int:
    from super_memory.recall_benchmark import release_gate

    result = release_gate(
        config_path=args.config,
        cases_path=args.cases,
        min_cases=args.min_cases,
        limit=args.limit,
    )
    return _emit(result)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def command_backup(args: argparse.Namespace) -> int:
    _, source = _config_db(args.config)
    output = Path(args.output).expanduser().resolve(strict=False)
    manifest = Path(args.manifest).expanduser().resolve(strict=False)
    if not source.is_file():
        return _emit({"ok": False, "gate": "verified_backup", "error": "source_database_missing", "source": str(source)})
    if output == source:
        return _emit({"ok": False, "gate": "verified_backup", "error": "backup_must_differ_from_source"})
    if output.exists() or manifest.exists():
        return _emit({
            "ok": False,
            "gate": "verified_backup",
            "error": "immutable_release_artifact_already_exists",
            "output": str(output),
            "manifest": str(manifest),
        })

    source_evidence = _sqlite_evidence(source)
    if not source_evidence.get("ok"):
        return _emit({"ok": False, "gate": "verified_backup", "source": source_evidence})

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    try:
        source_uri = f"file:{source.as_posix()}?mode=ro"
        with sqlite3.connect(source_uri, uri=True, timeout=10) as src, sqlite3.connect(temporary) as dst:
            src.backup(dst)
        backup_evidence = _sqlite_evidence(temporary)
        if not backup_evidence.get("ok"):
            temporary.unlink(missing_ok=True)
            return _emit({"ok": False, "gate": "verified_backup", "backup": backup_evidence})
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    backup_evidence = _sqlite_evidence(output)
    table_match = source_evidence.get("tables") == backup_evidence.get("tables")
    payload = {
        "schema": 1,
        "kind": "super-memory-release-rollback",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "prepared",
        "database": {
            "source": str(source),
            "backup": str(output),
            "source_evidence": source_evidence,
            "backup_evidence": backup_evidence,
            "table_set_match": table_match,
        },
        "release": {
            "current_link": args.current_link,
            "previous_release": args.previous_release,
            "new_release": args.new_release,
            "service": args.service,
        },
        "rollback_command": args.rollback_command,
    }
    payload["ok"] = bool(backup_evidence.get("ok")) and table_match and bool(args.rollback_command)
    if not payload["ok"]:
        return _emit({**payload, "error": "backup_verification_or_rollback_command_failed"})
    _atomic_json(manifest, payload)
    return _emit({**payload, "manifest": str(manifest), "gate": "verified_backup"})


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must contain a JSON object")
    return value


def _verify_manifest(path: Path, *, config_path: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "error": "manifest_missing", "manifest": str(path)}
    try:
        manifest = _load_manifest(path)
        database = manifest.get("database") or {}
        backup = Path(str(database.get("backup") or "")).expanduser().resolve(strict=False)
        if config_path:
            _, trusted_source = _config_db(config_path)
            manifest_source = Path(str(database.get("source") or "")).expanduser().resolve(strict=False)
            if manifest_source != trusted_source:
                return {"ok": False, "gate": "backup_manifest_verification", "manifest": str(path), "error": "manifest_source_mismatch", "trusted_source": str(trusted_source), "manifest_source": str(manifest_source)}
        # Backup is a release artifact: require it to live next to the manifest
        # or below that directory so a tampered manifest cannot point rollback
        # at an arbitrary local SQLite file.
        manifest_root = path.parent.resolve(strict=False)
        try:
            backup.relative_to(manifest_root)
        except ValueError:
            return {"ok": False, "gate": "backup_manifest_verification", "manifest": str(path), "error": "backup_outside_manifest_root", "backup": str(backup), "manifest_root": str(manifest_root)}
        evidence = _sqlite_evidence(backup)
        expected_hash = (database.get("backup_evidence") or {}).get("sha256")
        hash_match = bool(expected_hash) and expected_hash == evidence.get("sha256")
        rollback_present = bool(str(manifest.get("rollback_command") or "").strip())
        ok = bool(evidence.get("ok")) and hash_match and rollback_present
        return {
            "ok": ok,
            "gate": "backup_manifest_verification",
            "manifest": str(path),
            "backup": evidence,
            "hash_match": hash_match,
            "rollback_command_present": rollback_present,
        }
    except Exception as exc:
        return {"ok": False, "manifest": str(path), "error": f"{type(exc).__name__}: {exc}"}


def command_verify_backup(args: argparse.Namespace) -> int:
    return _emit(_verify_manifest(Path(args.manifest).expanduser().resolve(strict=False), config_path=getattr(args, "config", None)))


def _request_json(url: str, timeout: float) -> tuple[int, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = int(response.status)
        body = response.read(1024 * 1024)
    try:
        payload: Any = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {"raw": body.decode("utf-8", errors="replace")[:1000]}
    return status, payload


def command_readiness(args: argparse.Namespace) -> int:
    attempts = max(1, min(int(args.attempts), 60))
    timeout = max(0.1, min(float(args.timeout), 10.0))
    interval = max(0.0, min(float(args.interval), 10.0))
    observations: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        try:
            status, payload = _request_json(args.url, timeout)
            ready = status == 200 and isinstance(payload, dict) and payload.get("ready") is True
            observations.append({"attempt": attempt, "status": status, "ready": ready})
            if ready:
                return _emit({
                    "ok": True,
                    "gate": "readiness",
                    "ready": True,
                    "url": args.url,
                    "attempts_used": attempt,
                    "observations": observations,
                })
        except Exception as exc:
            observations.append({"attempt": attempt, "error": f"{type(exc).__name__}: {exc}"})
        if attempt < attempts and interval:
            time.sleep(interval)
    return _emit({
        "ok": False,
        "gate": "readiness",
        "ready": False,
        "url": args.url,
        "attempts_used": attempts,
        "observations": observations,
    })


def command_smoke(args: argparse.Namespace) -> int:
    timeout = max(0.1, min(float(args.timeout), 10.0))
    try:
        status, payload = _request_json(args.url, timeout)
        key_ok = not args.require_json_key or (
            isinstance(payload, dict) and payload.get(args.require_json_key) is True
        )
        ok = 200 <= status < 300 and key_ok
        return _emit({
            "ok": ok,
            "gate": "bounded_smoke",
            "url": args.url,
            "status": status,
            "timeout_seconds": timeout,
            "required_json_key": args.require_json_key,
            "required_key_true": key_ok,
        })
    except Exception as exc:
        return _emit({
            "ok": False,
            "gate": "bounded_smoke",
            "url": args.url,
            "timeout_seconds": timeout,
            "error": f"{type(exc).__name__}: {exc}",
        })


def command_rollback(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve(strict=False)
    verification = _verify_manifest(manifest_path, config_path=getattr(args, "config", None))
    if not verification.get("ok"):
        return _emit({"ok": False, "gate": "rollback", "verification": verification})
    if not args.execute:
        return _emit({
            "ok": False,
            "gate": "rollback",
            "error": "explicit_execute_required",
            "manifest": str(manifest_path),
        })

    manifest = _load_manifest(manifest_path)
    database = manifest["database"]
    source = _config_db(args.config)[1] if getattr(args, "config", None) else Path(database["source"])
    backup = Path(database["backup"]).expanduser().resolve(strict=False)

    # Validate every rollback target before the first mutation. This prevents a
    # missing previous release from leaving the database rolled back while the
    # application symlink remains on the new release.
    release = manifest.get("release") or {}
    current_link_raw = str(release.get("current_link") or "").strip()
    previous_raw = str(release.get("previous_release") or "").strip()
    current_link: Path | None = None
    previous: Path | None = None
    if bool(current_link_raw) != bool(previous_raw):
        return _emit({
            "ok": False,
            "gate": "rollback",
            "error": "incomplete_release_rollback_target",
        })
    if current_link_raw and previous_raw:
        current_link = Path(current_link_raw)
        previous = Path(previous_raw)
        if not previous.is_dir():
            return _emit({
                "ok": False,
                "gate": "rollback",
                "error": "previous_release_missing",
                "previous_release": str(previous),
            })

    source.parent.mkdir(parents=True, exist_ok=True)
    temporary = source.with_name(f".{source.name}.rollback-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    try:
        backup_uri = f"file:{backup.as_posix()}?mode=ro"
        with sqlite3.connect(backup_uri, uri=True, timeout=10) as src, sqlite3.connect(temporary) as dst:
            src.backup(dst)
        restored = _sqlite_evidence(temporary)
        if not restored.get("ok"):
            return _emit({"ok": False, "gate": "rollback", "error": "restored_copy_invalid", "evidence": restored})
        os.replace(temporary, source)
    finally:
        temporary.unlink(missing_ok=True)

    symlink_restored = False
    if current_link is not None and previous is not None:
        replacement = current_link.with_name(f".{current_link.name}.rollback-{os.getpid()}")
        replacement.unlink(missing_ok=True)
        replacement.symlink_to(previous)
        os.replace(replacement, current_link)
        symlink_restored = True

    restored_evidence = _sqlite_evidence(source)
    return _emit({
        "ok": bool(restored_evidence.get("ok")),
        "gate": "rollback",
        "database_restored": True,
        "symlink_restored": symlink_restored,
        "service_restart_required": True,
        "evidence": restored_evidence,
    })


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def config_command(name: str, handler: Any) -> argparse.ArgumentParser:
        item = sub.add_parser(name)
        item.add_argument("--config", required=True)
        item.set_defaults(handler=handler)
        return item

    config_command("db-path", command_db_path)
    config_command("isolation", command_isolation)
    config_command("migration-dry-run", command_migration)

    recall = config_command("recall", command_recall)
    recall.add_argument("--cases", required=True)
    recall.add_argument("--min-cases", type=int, default=5)
    recall.add_argument("--limit", type=int, default=100)

    backup = config_command("backup", command_backup)
    backup.add_argument("--output", required=True)
    backup.add_argument("--manifest", required=True)
    backup.add_argument("--rollback-command", required=True)
    backup.add_argument("--current-link", default="")
    backup.add_argument("--previous-release", default="")
    backup.add_argument("--new-release", default="")
    backup.add_argument("--service", default="")

    verify = sub.add_parser("verify-backup")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--config")
    verify.set_defaults(handler=command_verify_backup)

    readiness = sub.add_parser("readiness")
    readiness.add_argument("--url", required=True)
    readiness.add_argument("--attempts", type=int, default=15)
    readiness.add_argument("--timeout", type=float, default=2.0)
    readiness.add_argument("--interval", type=float, default=1.0)
    readiness.set_defaults(handler=command_readiness)

    smoke = sub.add_parser("smoke")
    smoke.add_argument("--url", required=True)
    smoke.add_argument("--timeout", type=float, default=3.0)
    smoke.add_argument("--require-json-key", default="")
    smoke.set_defaults(handler=command_smoke)

    rollback = sub.add_parser("rollback")
    rollback.add_argument("--manifest", required=True)
    rollback.add_argument("--config")
    rollback.add_argument("--execute", action="store_true")
    rollback.set_defaults(handler=command_rollback)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
