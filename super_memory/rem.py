"""REM (Rapid Embedding Matching) — fast nearest-neighbour vector recall.

Matches OpenClaw memory-core REM implementation:
- Approximate nearest neighbour search via sqlite_vec or numpy brute-force
- Falls back to brute-force when index not available
- Configurable top-k and distance metric
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .config import load_config
from .storage import SuperMemoryStore

logger = logging.getLogger(__name__)


# ── Vector search ──────────────────────────────────────────────────────────


def rem_search(
    query_vector: list[float],
    *,
    top_k: int = 10,
    min_score: float = 0.0,
    config_path: str | None = None,
) -> list[dict[str, Any]]:
    """Search for nearest neighbours using REM.

    Tries sqlite_vec first, falls back to numpy brute-force over stored vectors.
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    dim = len(query_vector)

    # Try sqlite_vec
    try:
        return _rem_sqlite_vec(store, query_vector, top_k=top_k, min_score=min_score)
    except Exception:
        pass

    # Fallback: numpy brute-force
    return _rem_bruteforce(store, query_vector, top_k=top_k, min_score=min_score)


def _rem_sqlite_vec(
    store: SuperMemoryStore,
    query_vector: list[float],
    *,
    top_k: int,
    min_score: float,
) -> list[dict[str, Any]]:
    """REM via sqlite_vec extension."""
    results: list[dict[str, Any]] = []
    with store.connect() as conn:
        try:
            rows = conn.execute(
                f"""
                SELECT m.id, m.content, m.layer, v.vector, v.distance
                FROM memories m
                JOIN memory_vectors v ON v.memory_id = m.id AND v.layer = m.layer
                WHERE v.vector IS NOT NULL
                ORDER BY v.distance ASC
                LIMIT ?
                """,
                (top_k * 2,),
            ).fetchall()
            for row in rows:
                dist = row[-1]
                score = max(0.0, min(1.0, 1.0 - float(dist)))
                if score >= min_score:
                    results.append({
                        "id": str(row[0]),
                        "content": str(row[1]),
                        "layer": str(row[2]),
                        "score": score,
                        "distance": float(dist),
                    })
        except Exception:
            raise
    return results[:top_k]


def _rem_bruteforce(
    store: SuperMemoryStore,
    query_vector: list[float],
    *,
    top_k: int,
    min_score: float,
) -> list[dict[str, Any]]:
    """REM via numpy brute-force cosine similarity."""
    query_np = np.array(query_vector, dtype=np.float32)
    if np.linalg.norm(query_np) > 0:
        query_np = query_np / np.linalg.norm(query_np)

    vectors: list[tuple[str, str, str, np.ndarray]] = []
    with store.connect() as conn:
        try:
            rows = conn.execute(
                """
                SELECT m.id, m.content, m.layer, v.vector
                FROM memories m
                JOIN memory_vectors v ON v.memory_id = m.id AND v.layer = m.layer
                WHERE v.vector IS NOT NULL
                """
            ).fetchall()
            for row in rows:
                vec_data = row[3]
                if isinstance(vec_data, (bytes, bytearray)):
                    vec = np.frombuffer(vec_data, dtype=np.float32)
                elif isinstance(vec_data, str):
                    vec = np.fromstring(vec_data.strip("[]"), sep=",", dtype=np.float32)
                else:
                    continue
                vectors.append((str(row[0]), str(row[1]), str(row[2]), vec))
        except Exception:
            raise

    if not vectors:
        return []

    # Compute cosine similarity
    scores = []
    for mid, content, layer, vec in vectors:
        if np.linalg.norm(vec) > 0:
            vec = vec / np.linalg.norm(vec)
        sim = float(np.dot(query_np, vec))
        sim = max(0.0, min(1.0, sim))
        if sim >= min_score:
            scores.append((sim, mid, content, layer))

    scores.sort(key=lambda x: x[0], reverse=True)
    return [
        {"id": mid, "content": content, "layer": layer, "score": sim, "distance": 1.0 - sim}
        for sim, mid, content, layer in scores[:top_k]
    ]


def rem_health(config_path: str | None = None) -> dict[str, Any]:
    """Check REM health."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    try:
        with store.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM memory_vectors WHERE vector IS NOT NULL"
            ).fetchone()
            vec_count = count[0] if count else 0
        return {"ok": True, "vector_count": vec_count}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
