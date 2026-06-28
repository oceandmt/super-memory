from __future__ import annotations

import json
from typing import Any

from ..config import load_config
from ..storage import SuperMemoryStore
from .fingerprint import normalize_for_dedup, hamming_distance
from .migrations import ensure_schema


def _tokens(text: str) -> set[str]:
    return {t for t in normalize_for_dedup(text).split() if len(t) > 2}


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def soft_delete_duplicate_clusters(*, threshold: float = 0.92, simhash_distance: int = 3, limit: int = 500, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    clusters = []
    with store.connect() as conn:
        ensure_schema(conn)
        # Backfill fingerprints for legacy or manually inserted canonical rows.
        from .outbox import register_memory
        from ..storage import row_to_memory
        legacy = conn.execute("""
            SELECT m.* FROM memories m LEFT JOIN memory_fingerprints f ON f.memory_id=m.id AND f.layer=m.layer
            WHERE m.layer='workspace_markdown' AND f.memory_id IS NULL
              AND COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0) != 1
            LIMIT ?
        """, (limit,)).fetchall()
        for lr in legacy:
            try:
                register_memory(conn, row_to_memory(lr), lr["layer"], enqueue_embed=False)
            except Exception:
                pass
        rows = conn.execute(
            """
            SELECT m.id, m.layer, m.content, m.metadata_json, f.normalized_hash, f.simhash
            FROM memories m LEFT JOIN memory_fingerprints f ON f.memory_id=m.id AND f.layer=m.layer
            WHERE m.layer='workspace_markdown' AND COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0) != 1
            ORDER BY m.created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        seen = set()
        for i, a in enumerate(rows):
            if a["id"] in seen:
                continue
            dup_ids = []
            for b in rows[i+1:]:
                if b["id"] in seen or a["id"] == b["id"]:
                    continue
                same_hash = a["normalized_hash"] and a["normalized_hash"] == b["normalized_hash"]
                near_hash = a["simhash"] is not None and b["simhash"] is not None and hamming_distance(int(a["simhash"]), int(b["simhash"])) <= simhash_distance
                semantic = _jaccard(a["content"], b["content"]) >= threshold
                if same_hash or (near_hash and semantic) or semantic:
                    dup_ids.append(b["id"])
                    seen.add(b["id"])
            if dup_ids:
                seen.add(a["id"])
                clusters.append({"canonical": a["id"], "duplicates": dup_ids})
        if not dry_run:
            for c in clusters:
                canonical = c["canonical"]
                for dup in c["duplicates"]:
                    conn.execute(
                        """
                        UPDATE memories SET metadata_json=json_set(
                          json_set(COALESCE(metadata_json,'{}'), '$.soft_deleted', 1),
                          '$.merged_into', ?
                        ) WHERE id=?
                        """,
                        (canonical, dup),
                    )
    return {"ok": True, "dry_run": dry_run, "cluster_count": len(clusters), "clusters": clusters[:50]}
