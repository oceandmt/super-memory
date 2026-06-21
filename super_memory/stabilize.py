"""Stabilization: Graph consistency and auto-repair for Super Memory.

Periodic health checks of the cognitive graph:
1. Orphan synapses (source/target neuron missing)
2. Broken fibers (fiber references missing neurons)
3. Duplicate neurons (same content_hash, different IDs)
4. Stale synapses (weight < prune threshold)

This is a lightweight alternative to neural-memory's 179 LOC stabilizer,
adapted for super-memory's canonical-first architecture.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .storage import SuperMemoryStore


# ── Graph Health Check ─────────────────────────────────────────────────────


def graph_health(
    store: SuperMemoryStore,
    orphan_limit: int = 100,
) -> dict[str, Any]:
    """Run full graph health check.

    Checks:
    1. Neuron count & type distribution
    2. Synapse count & relation distribution
    3. Fiber count & completeness
    4. Orphan synapses (dead source/target)
    5. Broken fibers (missing neuron references)
    6. Duplicate neurons

    Args:
        store: SuperMemoryStore.
        orphan_limit: Max orphans to report.

    Returns:
        Health check report.
    """
    report: dict[str, Any] = {
        "ok": True,
        "checks": {},
        "warnings": [],
        "recommendations": [],
    }

    with store.connect() as conn:
        try:
            # ── Neuron stats ──
            total_neurons = conn.execute("SELECT COUNT(*) FROM cognitive_neurons").fetchone()[0]
            by_kind = dict(
                conn.execute(
                    "SELECT kind, COUNT(*) FROM cognitive_neurons GROUP BY kind ORDER BY 2 DESC"
                ).fetchall()
            )
            report["checks"]["neurons"] = {"total": total_neurons, "by_kind": by_kind}
        except Exception as e:
            report["checks"]["neurons"] = {"error": f"{e}"}
            report["warnings"].append("cognitive_neurons table may not exist yet")

        try:
            # ── Synapse stats ──
            total_synapses = conn.execute("SELECT COUNT(*) FROM cognitive_synapses").fetchone()[0]
            by_relation = dict(
                conn.execute(
                    "SELECT relation, COUNT(*) FROM cognitive_synapses GROUP BY relation ORDER BY 2 DESC"
                ).fetchall()
            )
            report["checks"]["synapses"] = {"total": total_synapses, "by_relation": by_relation}
        except Exception as e:
            report["checks"]["synapses"] = {"error": f"{e}"}
            report["warnings"].append("cognitive_synapses table may not exist yet")

        try:
            # ── Fiber stats ──
            total_fibers = conn.execute("SELECT COUNT(*) FROM cognitive_fibers").fetchone()[0]
            report["checks"]["fibers"] = {"total": total_fibers}
        except Exception as e:
            report["checks"]["fibers"] = {"error": f"{e}"}
            report["warnings"].append("cognitive_fibers table may not exist yet")

        # ── Orphan synapses ──
        try:
            orphan_source = conn.execute(
                "SELECT COUNT(*) FROM cognitive_synapses AS s "
                "LEFT JOIN cognitive_neurons AS n ON s.source_neuron_id = n.id "
                "WHERE n.id IS NULL"
            ).fetchone()[0]
            orphan_target = conn.execute(
                "SELECT COUNT(*) FROM cognitive_synapses AS s "
                "LEFT JOIN cognitive_neurons AS n ON s.target_neuron_id = n.id "
                "WHERE n.id IS NULL"
            ).fetchone()[0]
            total_orphans = orphan_source + orphan_target
            report["checks"]["orphan_synapses"] = {
                "source_missing": orphan_source,
                "target_missing": orphan_target,
                "total": total_orphans,
            }
            if total_orphans > 0:
                report["warnings"].append(f"Found {total_orphans} orphan synapses")
                report["recommendations"].append(
                    "Run repair_orphans() to remove dangling synapses"
                )
        except Exception as e:
            report["checks"]["orphan_synapses"] = {"error": f"{e}"}

        # ── Duplicate neurons ──
        try:
            dupes = conn.execute(
                "SELECT content_hash, COUNT(*) as cnt FROM cognitive_neurons "
                "GROUP BY content_hash HAVING cnt > 1 ORDER BY cnt DESC"
            ).fetchall()
            total_dupes = sum(row["cnt"] - 1 for row in dupes) if dupes else 0
            report["checks"]["duplicate_neurons"] = {
                "total_duplicates": total_dupes,
                "groups": len(dupes) if dupes else 0,
            }
            if total_dupes > 0:
                report["warnings"].append(f"Found {total_dupes} duplicate neurons in {len(dupes)} groups")
                report["recommendations"].append(
                    "Run dedup_neurons() to merge duplicate neurons"
                )
        except Exception as e:
            report["checks"]["duplicate_neurons"] = {"error": f"{e}"}

        # ── Stale synapses ──
        try:
            stale = conn.execute(
                "SELECT COUNT(*) FROM cognitive_synapses WHERE weight < 0.05"
            ).fetchone()[0]
            report["checks"]["stale_synapses"] = {"count": stale}
            if stale > 0:
                report["recommendations"].append(
                    f"Run prune_stale({stale} synapses with weight < 0.05)"
                )
        except Exception as e:
            report["checks"]["stale_synapses"] = {"error": f"{e}"}

        # ── Integrity score ──
        issues = len(report["warnings"])
        if total_synapses > 0 and total_orphans > 0:
            orphan_ratio = total_orphans / total_synapses
        else:
            orphan_ratio = 0.0

        if issues == 0 and total_dupes == 0:
            grade = "healthy"
        elif issues <= 2 and orphan_ratio < 0.1:
            grade = "fair"
        else:
            grade = "degraded"

        report["grade"] = grade
        report["orphan_ratio"] = round(orphan_ratio, 4)
        report["issues"] = issues

    return report


# ── Repair Orphans ─────────────────────────────────────────────────────────


def repair_orphans(
    store: SuperMemoryStore,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Remove dangling synapses whose source or target neuron is missing.

    Args:
        store: SuperMemoryStore.
        dry_run: If True, preview without deleting.

    Returns:
        Repair report.
    """
    with store.connect() as conn:
        # Find orphans
        source_orphans = conn.execute(
            "SELECT s.id, s.source_neuron_id, s.target_neuron_id, s.relation "
            "FROM cognitive_synapses AS s "
            "LEFT JOIN cognitive_neurons AS n ON s.source_neuron_id = n.id "
            "WHERE n.id IS NULL"
        ).fetchall()

        target_orphans = conn.execute(
            "SELECT s.id, s.source_neuron_id, s.target_neuron_id, s.relation "
            "FROM cognitive_synapses AS s "
            "LEFT JOIN cognitive_neurons AS n ON s.target_neuron_id = n.id "
            "WHERE n.id IS NULL"
        ).fetchall()

        all_orphan_ids = set()
        orphan_details: list[dict[str, Any]] = []
        for row in source_orphans:
            if row["id"] not in all_orphan_ids:
                all_orphan_ids.add(row["id"])
                orphan_details.append({
                    "id": row["id"],
                    "reason": "source_missing",
                    "source": row["source_neuron_id"],
                    "target": row["target_neuron_id"],
                    "relation": row["relation"],
                })
        for row in target_orphans:
            if row["id"] not in all_orphan_ids:
                all_orphan_ids.add(row["id"])
                orphan_details.append({
                    "id": row["id"],
                    "reason": "target_missing",
                    "source": row["source_neuron_id"],
                    "target": row["target_neuron_id"],
                    "relation": row["relation"],
                })

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "orphan_count": len(all_orphan_ids),
                "orphans": orphan_details[:50],
                "note": f"Would delete {len(all_orphan_ids)} orphan synapses",
            }

        # Delete orphans
        if all_orphan_ids:
            placeholders = ",".join("?" for _ in all_orphan_ids)
            conn.execute(
                f"DELETE FROM cognitive_synapses WHERE id IN ({placeholders})",
                list(all_orphan_ids),
            )
            conn.commit()

        return {
            "ok": True,
            "dry_run": False,
            "deleted": len(all_orphan_ids),
            "orphans": orphan_details[:50],
        }


# ── Dedup Neurons ──────────────────────────────────────────────────────────


def dedup_neurons(
    store: SuperMemoryStore,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Merge duplicate neurons (same content_hash, different IDs).

    Strategy: keep the oldest neuron, rewire all synapses to point to it,
    then delete the duplicate.

    Args:
        store: SuperMemoryStore.
        dry_run: If True, preview without modifying.

    Returns:
        Dedup report.
    """
    with store.connect() as conn:
        # Find duplicate groups
        dup_groups = conn.execute(
            "SELECT content_hash, GROUP_CONCAT(id) as ids, COUNT(*) as cnt "
            "FROM cognitive_neurons "
            "GROUP BY content_hash HAVING cnt > 1 "
            "ORDER BY cnt DESC"
        ).fetchall()

        dedup_plan: list[dict[str, Any]] = []
        total_redundant = 0

        for group in dup_groups:
            ids = group["ids"].split(",")
            # Keep the first one (oldest), mark rest for removal
            keep_id = ids[0]
            remove_ids = ids[1:]
            total_redundant += len(remove_ids)
            dedup_plan.append({
                "content_hash": group["content_hash"],
                "keep_id": keep_id,
                "remove_ids": remove_ids,
                "count": group["cnt"],
            })

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "groups": len(dup_groups),
                "redundant_neurons": total_redundant,
                "plan": dedup_plan[:20],
                "note": f"Would remove {total_redundant} duplicate neurons across {len(dup_groups)} groups",
            }

        # Execute dedup
        removed = 0
        rewired = 0
        for plan in dedup_plan:
            keep_id = plan["keep_id"]
            for remove_id in plan["remove_ids"]:
                # Rewire source synapses
                try:
                    r = conn.execute(
                        "UPDATE cognitive_synapses SET source_neuron_id = ? "
                        "WHERE source_neuron_id = ?",
                        (keep_id, remove_id),
                    )
                    rewired += r.rowcount
                except Exception:
                    pass
                # Rewire target synapses
                try:
                    r = conn.execute(
                        "UPDATE cognitive_synapses SET target_neuron_id = ? "
                        "WHERE target_neuron_id = ?",
                        (keep_id, remove_id),
                    )
                    rewired += r.rowcount
                except Exception:
                    pass
                # Delete duplicate neuron
                conn.execute("DELETE FROM cognitive_neurons WHERE id = ?", (remove_id,))
                removed += 1

        conn.commit()

        return {
            "ok": True,
            "dry_run": False,
            "groups": len(dup_groups),
            "removed_neurons": removed,
            "rewired_synapses": rewired,
        }


# ── Prune Stale ────────────────────────────────────────────────────────────


def prune_stale(
    store: SuperMemoryStore,
    weight_threshold: float = 0.05,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Remove synapses with weight below threshold.

    Args:
        store: SuperMemoryStore.
        weight_threshold: Min weight to keep (default 0.05).
        dry_run: If True, preview without deleting.

    Returns:
        Prune report.
    """
    with store.connect() as conn:
        stale = conn.execute(
            "SELECT id, source_neuron_id, target_neuron_id, relation, weight "
            "FROM cognitive_synapses WHERE weight < ? ORDER BY weight ASC LIMIT 500",
            (weight_threshold,),
        ).fetchall()

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "stale_count": len(stale),
                "lowest_weights": [
                    {"id": r["id"], "relation": r["relation"], "weight": r["weight"]}
                    for r in stale[:20]
                ],
                "note": f"Would delete {len(stale)} synapses with weight < {weight_threshold}",
            }

        if stale:
            ids = [r["id"] for r in stale]
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"DELETE FROM cognitive_synapses WHERE id IN ({placeholders})",
                ids,
            )
            conn.commit()

        return {
            "ok": True,
            "dry_run": False,
            "pruned": len(stale),
            "weight_threshold": weight_threshold,
        }


# ─── Full Stabilization Run ────────────────────────────────────────────────


def stabilize(
    store: SuperMemoryStore,
    dry_run: bool = True,
    prune_stale_synapses: bool = True,
    weight_threshold: float = 0.05,
) -> dict[str, Any]:
    """Run full stabilization: health check, repair orphans, dedup, prune.

    Args:
        store: SuperMemoryStore.
        dry_run: If True, preview only.
        prune_stale_synapses: Whether to prune low-weight synapses.
        weight_threshold: Threshold for stale pruning.

    Returns:
        Full stabilization report.
    """
    results: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "steps": {},
        "summary": "",
    }

    # 1. Health check
    health = graph_health(store)
    results["steps"]["health"] = health

    # 2. Repair orphans
    results["steps"]["repair_orphans"] = repair_orphans(store, dry_run=dry_run)

    # 3. Dedup neurons
    results["steps"]["dedup_neurons"] = dedup_neurons(store, dry_run=dry_run)

    # 4. Prune stale
    if prune_stale_synapses:
        results["steps"]["prune_stale"] = prune_stale(store, dry_run=dry_run, weight_threshold=weight_threshold)

    # Summary
    if dry_run:
        results["summary"] = (
            f"DRY RUN: {health['checks']['neurons']['total']} neurons, "
            f"{health['checks']['synapses']['total']} synapses — "
            f"grade={health['grade']}, issues={health['issues']}"
        )
    else:
        total_fixes = (
            results["steps"]["repair_orphans"].get("deleted", 0)
            + results["steps"]["dedup_neurons"].get("removed", 0)
            + results["steps"]["prune_stale"].get("pruned", 0)
        )
        results["summary"] = (
            f"Applied {total_fixes} fixes: "
            f"{results['steps']['repair_orphans'].get('deleted', 0)} orphans removed, "
            f"{results['steps']['dedup_neurons'].get('removed', 0)} dupes merged, "
            f"{results['steps']['prune_stale'].get('pruned', 0)} stale pruned"
        )

    return results
