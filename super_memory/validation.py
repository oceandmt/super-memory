"""Operational validation helpers for vector and graph coverage."""
from __future__ import annotations
from typing import Any
from .config import load_config
from .storage import SuperMemoryStore
from . import graph as _graph


def vector_coverage(config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        active = conn.execute("""
            SELECT COUNT(DISTINCT id) c FROM memories
            WHERE layer='workspace_markdown'
              AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1
        """).fetchone()["c"]
        has_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_vectors'").fetchone() is not None
        vectors = 0
        if has_table:
            vectors = conn.execute("SELECT COUNT(DISTINCT memory_id) c FROM memory_vectors").fetchone()["c"]
    coverage = vectors / max(active, 1)
    return {"ok": True, "active_canonical": active, "vectorized_memories": vectors, "coverage": round(coverage, 4), "has_memory_vectors_table": has_table}


def graph_multihop_validation(query: str = "super memory project recall graph", limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    stats = _graph.stats(config_path=config_path)
    recall = _graph.spreading_activation(query, depth=2, top_k=limit, seed_limit=max(limit, 20), config_path=config_path)
    neurons = sum((stats.get("neurons") or {}).values()) if isinstance(stats.get("neurons"), dict) else 0
    synapses = sum((stats.get("synapses") or {}).values()) if isinstance(stats.get("synapses"), dict) else 0
    hits = len(recall.get("activated", []) or recall.get("results", []) or recall.get("fibers", []) or [])
    return {"ok": bool(stats.get("ok")) and neurons > 0 and synapses > 0, "query": query, "neurons_total": neurons, "synapses_total": synapses, "hits": hits, "stats": stats, "recall": recall}
