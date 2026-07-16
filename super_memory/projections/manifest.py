"""Revision-aware manifest for projections derived from canonical memories."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..canonical_contract import (
    CANONICAL_CONTRACT_VERSION,
    DEFAULT_CANONICAL_LAYER,
    canonical_id,
    canonical_revision,
    content_hash,
    projection_id,
    source_revision,
)
from ..config import load_config
from ..storage import SuperMemoryStore

_ALLOWED_STATUSES = {"active", "stale", "orphaned"}
_DEFAULT_LIMIT = 200
_MAX_LIMIT = 5_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_limit(limit: int) -> int:
    return min(max(int(limit), 1), _MAX_LIMIT)


def _manifest_columns(conn) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(projection_manifest)").fetchall()
    }


def ensure_manifest(conn) -> list[str]:
    """Create/additively upgrade the projection manifest, preserving all rows."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projection_manifest (
            projection_id TEXT PRIMARY KEY,
            memory_id TEXT NOT NULL,
            canonical_id TEXT,
            canonical_layer TEXT NOT NULL DEFAULT 'workspace_markdown',
            projection_type TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_revision TEXT,
            projection_hash TEXT,
            adapter_name TEXT,
            adapter_version TEXT,
            contract_version TEXT NOT NULL DEFAULT '1',
            status TEXT NOT NULL DEFAULT 'active',
            status_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_verified_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )"""
    )
    additions = (
        ("canonical_id", "ALTER TABLE projection_manifest ADD COLUMN canonical_id TEXT"),
        (
            "canonical_layer",
            "ALTER TABLE projection_manifest ADD COLUMN canonical_layer "
            "TEXT NOT NULL DEFAULT 'workspace_markdown'",
        ),
        (
            "source_revision",
            "ALTER TABLE projection_manifest ADD COLUMN source_revision TEXT",
        ),
        (
            "contract_version",
            "ALTER TABLE projection_manifest ADD COLUMN contract_version "
            "TEXT NOT NULL DEFAULT '1'",
        ),
        (
            "status_reason",
            "ALTER TABLE projection_manifest ADD COLUMN status_reason TEXT",
        ),
        (
            "last_verified_at",
            "ALTER TABLE projection_manifest ADD COLUMN last_verified_at TEXT",
        ),
    )
    changed: list[str] = []
    cols = _manifest_columns(conn)
    for column, statement in additions:
        if column not in cols:
            conn.execute(statement)
            changed.append(f"projection_manifest.{column}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projection_manifest_memory "
        "ON projection_manifest(memory_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projection_manifest_type_status "
        "ON projection_manifest(projection_type,status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projection_manifest_canonical "
        "ON projection_manifest(canonical_id,source_revision)"
    )

    # This is an identity/schema backfill, not a currentness assertion. Existing
    # source_hash values remain untouched and are checked against canonical data
    # by audit_projection_drift before a row can be considered current.
    rows = conn.execute(
        "SELECT projection_id,memory_id,canonical_layer,source_hash,canonical_id,"
        "source_revision,contract_version FROM projection_manifest"
    ).fetchall()
    for row in rows:
        layer = row[2] or DEFAULT_CANONICAL_LAYER
        updates: dict[str, str] = {}
        if not row[4]:
            updates["canonical_id"] = canonical_id(row[1], layer)
        if not row[5]:
            try:
                updates["source_revision"] = source_revision(row[3])
            except ValueError:
                updates["source_revision"] = "unverified"
        if not row[6]:
            updates["contract_version"] = CANONICAL_CONTRACT_VERSION
        if "canonical_id" in updates:
            conn.execute(
                "UPDATE projection_manifest SET canonical_id=? WHERE projection_id=?",
                (updates["canonical_id"], row[0]),
            )
        if "source_revision" in updates:
            conn.execute(
                "UPDATE projection_manifest SET source_revision=? WHERE projection_id=?",
                (updates["source_revision"], row[0]),
            )
        if "contract_version" in updates:
            conn.execute(
                "UPDATE projection_manifest SET contract_version=? WHERE projection_id=?",
                (updates["contract_version"], row[0]),
            )
    return changed


def hash_text(text: str) -> str:
    """Backward-compatible alias for the canonical SHA-256 function."""
    return content_hash(text)


def _canonical_row(conn, memory_id: str, layer: str):
    return conn.execute(
        """SELECT id,layer,content FROM memories
           WHERE id=? AND layer=?
             AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1
           LIMIT 1""",
        (memory_id, layer),
    ).fetchone()


def register_projection(
    memory_id: str,
    projection_type: str,
    source_content: str = "",
    projection_content: str = "",
    adapter_name: str = "super-memory",
    adapter_version: str = "1",
    status: str = "active",
    metadata: dict[str, Any] | None = None,
    config_path: str | None = None,
    canonical_layer: str = DEFAULT_CANONICAL_LAYER,
) -> dict[str, Any]:
    """Register one adapter projection of a canonical memory revision.

    If the canonical row exists, its actual content overrides caller-supplied
    ``source_content``. This prevents a stale or forged cached hash from being
    registered as current. Registering a missing canonical ID is retained for
    auditability but is immediately marked orphaned.
    """
    if status not in _ALLOWED_STATUSES:
        raise ValueError(f"invalid projection status: {status}")
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    now = _now()
    with store.connect() as conn:
        ensure_manifest(conn)
        row = _canonical_row(conn, memory_id, canonical_layer)
        canonical_content = str(row["content"] if row else source_content or "")
        revision = canonical_revision(memory_id, canonical_content, canonical_layer)
        desired_status = "orphaned" if row is None else status
        reason = "canonical_missing_or_deleted" if row is None else None
        pid = projection_id(revision, projection_type, adapter_name, adapter_version)
        projection_hash = content_hash(projection_content) if projection_content else None
        conn.execute(
            """INSERT INTO projection_manifest
               (projection_id,memory_id,canonical_id,canonical_layer,projection_type,
                source_hash,source_revision,projection_hash,adapter_name,adapter_version,
                contract_version,status,status_reason,created_at,updated_at,last_verified_at,
                metadata_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(projection_id) DO UPDATE SET
                 memory_id=excluded.memory_id,
                 canonical_id=excluded.canonical_id,
                 canonical_layer=excluded.canonical_layer,
                 projection_type=excluded.projection_type,
                 source_hash=excluded.source_hash,
                 source_revision=excluded.source_revision,
                 projection_hash=excluded.projection_hash,
                 adapter_name=excluded.adapter_name,
                 adapter_version=excluded.adapter_version,
                 contract_version=excluded.contract_version,
                 status=excluded.status,
                 status_reason=excluded.status_reason,
                 updated_at=excluded.updated_at,
                 last_verified_at=excluded.last_verified_at,
                 metadata_json=excluded.metadata_json""",
            (
                pid,
                memory_id,
                revision.canonical_id,
                canonical_layer,
                projection_type,
                revision.source_hash,
                revision.source_revision,
                projection_hash,
                adapter_name,
                adapter_version,
                CANONICAL_CONTRACT_VERSION,
                desired_status,
                reason,
                now,
                now,
                now if row is not None else None,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
    return {
        "ok": True,
        "projection_id": pid,
        "memory_id": memory_id,
        "canonical_id": revision.canonical_id,
        "source_hash": revision.source_hash,
        "source_revision": revision.source_revision,
        "projection_type": projection_type,
        "status": desired_status,
    }


def _classify(row: dict[str, Any]) -> tuple[str, str | None]:
    if row.get("content") is None:
        return "orphaned", "canonical_missing_or_deleted"
    actual = canonical_revision(
        row["memory_id"], row.get("content") or "", row.get("canonical_layer") or DEFAULT_CANONICAL_LAYER
    )
    checks = (
        (row.get("canonical_id") == actual.canonical_id, "canonical_id_mismatch"),
        (row.get("source_hash") == actual.source_hash, "source_hash_mismatch"),
        (row.get("source_revision") == actual.source_revision, "source_revision_mismatch"),
        (row.get("contract_version") == CANONICAL_CONTRACT_VERSION, "contract_version_mismatch"),
        (bool(row.get("adapter_name")), "adapter_name_missing"),
        (bool(row.get("adapter_version")), "adapter_version_missing"),
    )
    for valid, reason in checks:
        if not valid:
            return "stale", reason
    return "active", None


def audit_projection_drift(
    config_path: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Boundedly classify manifest rows without mutating the database."""
    limit = _bounded_limit(limit)
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        manifest_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='projection_manifest'"
        ).fetchone()
        manifest_columns = _manifest_columns(conn) if manifest_exists else set()
        layer_expr = (
            "COALESCE(p.canonical_layer,'workspace_markdown')"
            if "canonical_layer" in manifest_columns
            else "'workspace_markdown'"
        )
        rows = conn.execute(
            f"""SELECT p.*,m.content
               FROM projection_manifest p
               LEFT JOIN memories m
                 ON m.id=p.memory_id AND m.layer={layer_expr}
                AND COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0)!=1
               ORDER BY p.projection_id LIMIT ?""",
            (limit,),
        ).fetchall() if manifest_exists else []
        orphans: list[dict[str, Any]] = []
        stale: list[dict[str, Any]] = []
        status_mismatches: list[dict[str, Any]] = []
        for raw in rows:
            item = dict(raw)
            item.pop("content", None)
            desired, reason = _classify(dict(raw))
            item["desired_status"] = desired
            item["desired_status_reason"] = reason
            if desired == "orphaned":
                orphans.append(item)
            elif desired == "stale":
                stale.append(item)
            if item.get("status") != desired or item.get("status_reason") != reason:
                status_mismatches.append(item)

        manifest_match = (
            "AND p.canonical_layer=m.layer" if "canonical_layer" in manifest_columns else ""
        )
        if manifest_exists:
            missing_rows = conn.execute(
                f"""SELECT m.id,m.layer FROM memories m
                   WHERE m.layer=?
                     AND COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0)!=1
                     AND NOT EXISTS (
                       SELECT 1 FROM projection_manifest p
                        WHERE p.memory_id=m.id {manifest_match}
                     )
                   ORDER BY m.id LIMIT ?""",
                (DEFAULT_CANONICAL_LAYER, limit),
            ).fetchall()
        else:
            missing_rows = conn.execute(
                """SELECT id,layer FROM memories
                   WHERE layer=?
                     AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1
                   ORDER BY id LIMIT ?""",
                (DEFAULT_CANONICAL_LAYER, limit),
            ).fetchall()
        missing = [
            {
                "memory_id": row["id"],
                "canonical_layer": row["layer"],
                "reason": "no_projection_manifest",
            }
            for row in missing_rows
        ]
    return {
        "ok": True,
        "dry_run": True,
        "schema_missing": not bool(manifest_exists),
        "limit": limit,
        "scanned": len(rows),
        "orphans": orphans,
        "stale": stale,
        "missing": missing,
        "status_mismatches": status_mismatches,
        "counts": {
            "orphans": len(orphans),
            "stale": len(stale),
            "missing": len(missing),
            "status_mismatches": len(status_mismatches),
        },
    }


def repair_projection_drift(
    config_path: str | None = None,
    dry_run: bool = True,
    limit: int = _DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Apply deterministic status labels; dry-run by default and idempotent."""
    if dry_run:
        audit = audit_projection_drift(config_path=config_path, limit=limit)
        return {"ok": True, "dry_run": True, "audit": audit, "changed": 0}
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        ensure_manifest(conn)
        conn.commit()
    audit = audit_projection_drift(config_path=config_path, limit=limit)
    changed = 0
    now = _now()
    with store.connect() as conn:
        ensure_manifest(conn)
        for item in audit["status_mismatches"]:
            cursor = conn.execute(
                """UPDATE projection_manifest
                   SET status=?,status_reason=?,updated_at=?,last_verified_at=?
                   WHERE projection_id=?
                     AND (status!=? OR COALESCE(status_reason,'')!=COALESCE(?,''))""",
                (
                    item["desired_status"],
                    item["desired_status_reason"],
                    now,
                    now,
                    item["projection_id"],
                    item["desired_status"],
                    item["desired_status_reason"],
                ),
            )
            changed += max(cursor.rowcount, 0)
        conn.commit()
    return {"ok": True, "dry_run": False, "audit": audit, "changed": changed}


def backfill_projection_manifest(
    config_path: str | None = None,
    limit: int = 500,
    projection_type: str = "canonical_memory",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Plan/apply baseline manifest rows, defaulting to a bounded dry-run."""
    limit = _bounded_limit(limit)
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    planned: list[dict[str, str]] = []
    with store.connect() as conn:
        if not dry_run:
            ensure_manifest(conn)
        manifest_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='projection_manifest'"
        ).fetchone()
        rows = conn.execute(
            """SELECT id,layer,content FROM memories
               WHERE layer=?
                 AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1
               ORDER BY id LIMIT ?""",
            (DEFAULT_CANONICAL_LAYER, limit),
        ).fetchall()
        for row in rows:
            revision = canonical_revision(row["id"], row["content"] or "", row["layer"])
            pid = projection_id(revision, projection_type, "backfill", "1")
            exists = (
                conn.execute(
                    "SELECT 1 FROM projection_manifest WHERE projection_id=?", (pid,)
                ).fetchone()
                if manifest_exists
                else None
            )
            if not exists:
                planned.append({"projection_id": pid, "memory_id": row["id"]})
        if not dry_run:
            now = _now()
            by_id = {row["id"]: row for row in rows}
            for item in planned:
                row = by_id[item["memory_id"]]
                revision = canonical_revision(row["id"], row["content"] or "", row["layer"])
                conn.execute(
                    """INSERT OR IGNORE INTO projection_manifest
                       (projection_id,memory_id,canonical_id,canonical_layer,projection_type,
                        source_hash,source_revision,projection_hash,adapter_name,adapter_version,
                        contract_version,status,status_reason,created_at,updated_at,last_verified_at,
                        metadata_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        item["projection_id"], row["id"], revision.canonical_id, row["layer"],
                        projection_type, revision.source_hash, revision.source_revision, None,
                        "backfill", "1", CANONICAL_CONTRACT_VERSION, "active", None,
                        now, now, now, json.dumps({"backfill": True}, sort_keys=True),
                    ),
                )
            conn.commit()
    return {
        "ok": True,
        "dry_run": dry_run,
        "changed": 0 if dry_run else len(planned),
        "planned": planned,
        "limit": limit,
        "projection_type": projection_type,
    }
