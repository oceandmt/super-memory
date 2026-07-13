"""Lightweight Brain Versioning for Super Memory.

Creates deterministic snapshots of memory state for safe experimentation.
Supports:
1. Create snapshot (current state dump)
2. List snapshots
3. Diff between two snapshots
4. Rollback to a snapshot (dry-run by default)

Unlike neural-memory's 438 LOC versioning, this is ~200 LOC
focused on the essential: snapshot + diff + rollback.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .storage import SuperMemoryStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot_key(version_id: str) -> str:
    return f"version:v1:{version_id}"


def _snapshot_index_key() -> str:
    return "version:v1:index"


def create_snapshot(
    store: SuperMemoryStore,
    name: str = "snapshot",
    description: str = "",
) -> dict[str, Any]:
    """Create a full memory state snapshot.

    Captures:
    - Total active memory count
    - Layer distribution
    - Type distribution
    - Graph neuron/synapse/fiber counts
    - First 5 memory IDs (for diff reference)

    Args:
        store: SuperMemoryStore.
        name: Snapshot name.
        description: Optional description.

    Returns:
        Dict with snapshot metadata.
    """
    version_id = str(uuid4())[:8]
    ts = _now()

    with store.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        from .models import ALIVE_SQL
        active_filter = ALIVE_SQL  # canonical soft-delete guard (see models.ALIVE_SQL)
        active = conn.execute(
            f"SELECT COUNT(*) FROM memories WHERE {active_filter}"
        ).fetchone()[0]
        by_layer = dict(
            conn.execute("SELECT layer, COUNT(*) FROM memories GROUP BY layer").fetchall()
        )
        by_type = dict(
            conn.execute("SELECT type, COUNT(*) FROM memories GROUP BY type ORDER BY 2 DESC").fetchall()
        )
        # Graph state
        neurons = 0
        synapses = 0
        fibers = 0
        try:
            neurons = conn.execute("SELECT COUNT(*) FROM cognitive_neurons").fetchone()[0]
            synapses = conn.execute("SELECT COUNT(*) FROM cognitive_synapses").fetchone()[0]
            fibers = conn.execute("SELECT COUNT(*) FROM cognitive_fibers").fetchone()[0]
        except Exception:
            pass

        # Sample memory IDs for later diff
        sample_ids = [
            r["id"] for r in
            conn.execute(
                "SELECT id, SUBSTR(content, 1, 100) as preview FROM memories WHERE " + active_filter + " ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
        ]

    snapshot = {
        "version_id": version_id,
        "name": name,
        "description": description,
        "created_at": ts,
        "total": total,
        "active": active,
        "by_layer": {k: v for k, v in by_layer.items()},
        "by_type": {k: v for k, v in by_type.items()},
        "graph_neurons": neurons,
        "graph_synapses": synapses,
        "graph_fibers": fibers,
        "sample_ids": sample_ids,
    }

    # Store in meta table
    store._set_meta(_snapshot_key(version_id), snapshot)

    # Update index
    index = store._get_meta(_snapshot_index_key())
    if index:
        try:
            idx = json.loads(index)
        except (json.JSONDecodeError, TypeError):
            idx = []
    else:
        idx = []
    idx.insert(0, {"version_id": version_id, "name": name, "created_at": ts})
    store._set_meta(_snapshot_index_key(), idx[:50])  # Keep last 50

    return {"ok": True, **snapshot}


def list_snapshots(store: SuperMemoryStore, limit: int = 20) -> dict[str, Any]:
    """List all created snapshots."""
    index_raw = store._get_meta(_snapshot_index_key())
    if not index_raw:
        return {"ok": True, "snapshots": []}
    try:
        idx = json.loads(index_raw)
    except (json.JSONDecodeError, TypeError):
        return {"ok": True, "snapshots": []}
    return {"ok": True, "snapshots": idx[:limit]}


def get_snapshot(store: SuperMemoryStore, version_id: str) -> dict[str, Any]:
    """Get full snapshot data."""
    raw = store._get_meta(_snapshot_key(version_id))
    if not raw:
        return {"ok": False, "error": f"snapshot not found: {version_id}"}
    try:
        return {"ok": True, **json.loads(raw)}
    except json.JSONDecodeError:
        return {"ok": False, "error": f"corrupt snapshot: {version_id}"}


def diff_snapshots(
    store: SuperMemoryStore,
    from_version: str,
    to_version: str,
) -> dict[str, Any]:
    """Compare two snapshots and return differences."""
    from_snap = get_snapshot(store, from_version)
    to_snap = get_snapshot(store, to_version)

    if not from_snap.get("ok"):
        return {"ok": False, "error": from_snap.get("error", f"invalid from_version: {from_version}")}
    if not to_snap.get("ok"):
        return {"ok": False, "error": to_snap.get("error", f"invalid to_version: {to_version}")}

    diffs: dict[str, Any] = {}
    for key in ("active", "total", "graph_neurons", "graph_synapses", "graph_fibers"):
        a = from_snap.get(key, 0)
        b = to_snap.get(key, 0)
        if a != b:
            diffs[key] = {"from": a, "to": b, "delta": b - a}

    # Layer diffs
    from_layers = from_snap.get("by_layer", {})
    to_layers = to_snap.get("by_layer", {})
    all_layers = set(from_layers.keys()) | set(to_layers.keys())
    layer_diffs = {}
    for layer in sorted(all_layers):
        a = from_layers.get(layer, 0)
        b = to_layers.get(layer, 0)
        if a != b:
            layer_diffs[layer] = {"from": a, "to": b, "delta": b - a}
    if layer_diffs:
        diffs["by_layer"] = layer_diffs

    return {
        "ok": True,
        "from": {"version_id": from_version, "name": from_snap.get("name", ""),
                 "created_at": from_snap.get("created_at", "")},
        "to": {"version_id": to_version, "name": to_snap.get("name", ""),
               "created_at": to_snap.get("created_at", "")},
        "diffs": diffs,
        "has_changes": bool(diffs),
    }


def rollback_dry_run(
    store: SuperMemoryStore,
    version_id: str,
) -> dict[str, Any]:
    """Preview what would change if rolling back to a snapshot.

    This is a dry-run that shows current state vs snapshot state.
    Actual rollback requires operator intervention (no automated
    destructive operations).
    """
    snap = get_snapshot(store, version_id)
    if not snap.get("ok"):
        return {"ok": False, "error": snap.get("error", f"invalid version: {version_id}")}

    with store.connect() as conn:
        current_active = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE "
            "(json_extract(metadata_json, '$.soft_deleted') IS NULL "
            "OR json_extract(metadata_json, '$.soft_deleted') != 1)"
        ).fetchone()[0]

    snapshot_active = snap.get("active", 0)

    return {
        "ok": True,
        "version_id": version_id,
        "snapshot_name": snap.get("name", ""),
        "snapshot_active": snapshot_active,
        "current_active": current_active,
        "delta": current_active - snapshot_active,
        "dry_run": True,
        "note": "Rollback is a manual process — review diffs and use prune/cleanup tools to revert.",
    }
