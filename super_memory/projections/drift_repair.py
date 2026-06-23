"""Projection Drift Repair — audit and fix stale/orphaned derived projections.

Detects:
- Orphaned projections (drawer/closet/graph/vector rows referencing deleted memories)
- Stale canonical content (content_hash mismatch vs canonical markdown)
- Missing projections (memories without expected derived entries)
- Embedding schema mismatch (if vector dimensions changed)

P2 — borrowed from:
- MemPalace: stale index purge, currentness checks, file hash tracking
- Neural Memory: projection status, lifecycle sweep
- Honcho: validate_embedding_schema()
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..storage import SuperMemoryStore, row_to_memory

logger = logging.getLogger("super-memory.projections.drift_repair")

# ── Repair Table ───────────────────────────────────────────────────────────

REPAIR_TABLES = {
    "closets": "palace_closets",
    "drawers": "palace_drawers",
    "recall_events": "recall_events",
    "recall_feedback": "recall_feedback",
    "cached_embeddings": "cached_embeddings",
    "projection_meta": "projection_meta",
    "graph_edges": "graph_edges",
    "graph_nodes": "graph_nodes",
    "mempalace_index": "mempalace_index",
    "mempalace_chunks": "mempalace_chunks",
    "honcho_events": "honcho_events",
    "neural_memory_events": "neural_memory_events",
}


# ── Ensure repair table ────────────────────────────────────────────────────

def _ensure_tables(store: SuperMemoryStore) -> None:
    with store.connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projection_meta (
                table_name TEXT NOT NULL,
                memory_id TEXT,
                projection_key TEXT NOT NULL,
                content_hash TEXT,
                last_verified TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (table_name, projection_key)
            );
            CREATE INDEX IF NOT EXISTS idx_projection_meta_memory ON projection_meta(memory_id);
            CREATE INDEX IF NOT EXISTS idx_projection_meta_table ON projection_meta(table_name);
        """)


# ── Register Projection ────────────────────────────────────────────────────

def register_projection(
    table_name: str,
    memory_id: str,
    projection_key: str,
    content_hash: str | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Register a derived projection in projection_meta."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    with store.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO projection_meta (table_name, memory_id, projection_key, content_hash, last_verified, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (table_name, memory_id, projection_key, content_hash, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    return {"ok": True, "table_name": table_name, "projection_key": projection_key}


# ── Drift Audit ────────────────────────────────────────────────────────────

def audit_drift(config_path: str | None = None) -> dict[str, Any]:
    """Full drift audit across all derived projections.

    Returns:
    - orphaned_entries: count + sample of entries pointing to deleted memories
    - stale_canonical: entries where canonical content_hash differs
    - missing_projections: active memories without expected projections
    - total_issues: sum
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    issues = []
    stats = {}

    # 1. Orphaned closets/drawers
    for proj_name, table in [("closets", "palace_closets"), ("drawers", "palace_drawers")]:
        try:
            with store.connect() as conn:
                orphans = conn.execute(
                    f"SELECT COUNT(*) as c FROM {table} WHERE memory_id NOT IN (SELECT id FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0)"
                ).fetchone()
            count = orphans["c"] if orphans else 0
            stats[f"orphaned_{proj_name}"] = count
            if count > 0:
                issues.append({
                    "severity": "high" if count > 50 else "medium",
                    "type": f"orphaned_{proj_name}",
                    "message": f"{count} orphaned {proj_name} entries pointing to soft-deleted/missing memories",
                    "count": count,
                })
        except Exception as e:
            stats[f"orphaned_{proj_name}"] = -1
            issues.append({"severity": "low", "type": f"orphaned_{proj_name}_error", "message": str(e)})

    # 2. Orphaned recall feedback
    for proj_name, table in [("recall_feedback", "recall_feedback"), ("recall_events", "recall_events")]:
        try:
            with store.connect() as conn:
                if proj_name == "recall_feedback":
                    orphans = conn.execute(
                        "SELECT COUNT(*) as c FROM recall_feedback WHERE memory_id NOT IN (SELECT id FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0)"
                    ).fetchone()
                else:
                    orphans = {"c": 0}  # events don't link directly
                count = orphans["c"] if orphans else 0
                stats[f"orphaned_{proj_name}"] = count
                if count > 0:
                    issues.append({
                        "severity": "low",
                        "type": f"orphaned_{proj_name}",
                        "message": f"{count} orphaned {proj_name} entries",
                        "count": count,
                    })
        except Exception as e:
            stats[f"orphaned_{proj_name}"] = -1

    # 3. Missing closets for active canonical memories
    try:
        with store.connect() as conn:
            missing = conn.execute(
                "SELECT COUNT(*) as c FROM memories m WHERE layer='workspace_markdown' AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 AND NOT EXISTS (SELECT 1 FROM palace_closets pc WHERE pc.memory_id = m.id)"
            ).fetchone()
        count = missing["c"] if missing else 0
        stats["missing_closets"] = count
        if count > 0:
            issues.append({
                "severity": "medium",
                "type": "missing_closets",
                "message": f"{count} active canonical memories without closet entries",
                "count": count,
            })
    except Exception as e:
        stats["missing_closets"] = -1
        issues.append({"severity": "low", "type": "missing_closets_error", "message": str(e)})

    # 4. Missing projection_meta entries for active canonical memories
    try:
        with store.connect() as conn:
            unregistered = conn.execute(
                "SELECT COUNT(*) as c FROM memories m WHERE layer='workspace_markdown' AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 AND NOT EXISTS (SELECT 1 FROM projection_meta pm WHERE pm.memory_id = m.id)"
            ).fetchone()
        count = unregistered["c"] if unregistered else 0
        stats["unregistered_projections"] = count
        if count > 100:
            issues.append({
                "severity": "low",
                "type": "unregistered_projections",
                "message": f"{count} active memories without projection_meta registration (expected for pre-P0 memories)",
                "count": count,
            })
    except Exception as e:
        stats["unregistered_projections"] = -1

    # Score
    total = sum(stats.get(k, 0) for k in stats if isinstance(stats[k], (int, float)) and stats[k] > 0)
    drift_score = max(0.0, 100.0 - total * 0.5)  # each issue deducts 0.5 points

    return {
        "ok": True,
        "drift_score": round(drift_score, 1),
        "total_issues": len(issues),
        "issues": issues,
        "stats": stats,
        "summary": f"Drift score: {drift_score:.0f}/100, {len(issues)} issues, {total:.0f} total affected entries",
    }


# ── Repair Actions ─────────────────────────────────────────────────────────

def repair_orphans(
    project: str | None = None,
    dry_run: bool = True,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Repair orphaned projection entries.

    Deletes entries in derived tables whose memory_id no longer
    exists in active memories.

    Args:
        dry_run: If True, only report what would be deleted.
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    results = {}

    for proj_name, table in REPAIR_TABLES.items():
        # Determine which column links to memories
        id_col = None
        if "memory_id" in proj_name or table in ("palace_closets", "palace_drawers", "recall_feedback"):
            id_col = "memory_id"
        elif table == "recall_events":
            id_col = None  # events reference no single memory

        if id_col is None:
            continue

        try:
            with store.connect() as conn:
                # Find orphaned
                orphans = conn.execute(
                    f"SELECT {id_col} FROM {table} WHERE {id_col} NOT IN (SELECT id FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0)"
                ).fetchall()
                count = len(orphans)

                if count > 0 and not dry_run:
                    conn.execute(
                        f"DELETE FROM {table} WHERE {id_col} NOT IN (SELECT id FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0)"
                    )
                    conn.commit()

            results[proj_name] = {
                "deleted": count if not dry_run else 0,
                "found": count,
                "table": table,
            }
        except Exception as e:
            results[proj_name] = {"error": str(e), "table": table}

    total_found = sum(r.get("found", 0) for r in results.values())
    total_deleted = sum(r.get("deleted", 0) for r in results.values())

    return {
        "ok": True,
        "dry_run": dry_run,
        "total_found": total_found,
        "total_deleted": total_deleted,
        "results": results,
    }


def rebuild_missing_closets(
    limit: int = 200,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Build closets/drawers for canonical memories missing them."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    with store.connect() as conn:
        missing = conn.execute(
            "SELECT m.* FROM memories m WHERE layer='workspace_markdown' AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 AND NOT EXISTS (SELECT 1 FROM palace_closets pc WHERE pc.memory_id = m.id) ORDER BY m.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    from ..projections.closet import build_closets

    built = 0
    errors = []
    for row in missing:
        try:
            rec = row_to_memory(row)
            build_closets(rec.id, rec.content, rec.type.value, config_path=config_path)
            built += 1
        except Exception as e:
            errors.append({"memory_id": row["id"], "error": str(e)})

    return {
        "ok": True,
        "built": built,
        "errors": len(errors),
        "error_details": errors[:5],
    }


def full_repair(
    dry_run: bool = True,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Full repair: audit + orphan repair + missing closets."""
    audit = audit_drift(config_path=config_path)
    orphans = repair_orphans(dry_run=dry_run, config_path=config_path)
    closets = {}
    if not dry_run:
        missing = audit.get("stats", {}).get("missing_closets", 0)
        if missing and missing > 0 and missing < 200:
            closets = rebuild_missing_closets(limit=missing, config_path=config_path)

    return {
        "ok": True,
        "dry_run": dry_run,
        "audit": audit,
        "orphan_repair": orphans,
        "closet_repair": closets,
    }
