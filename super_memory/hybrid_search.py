"""Hybrid search combining FTS5 text scores with vector similarity.

Matches OpenClaw memory-core hybrid search:
- Reciprocal Rank Fusion (RRF) fusion of text + vector scores
- Configurable text/vector weight ratio
- Fallback to pure text when vectors unavailable
- Normalized score range [0, 1]
"""

from __future__ import annotations

from typing import Any


# ── RRF Fusion ─────────────────────────────────────────────────────────────

RRF_K = 60  # RRF constant


def rrf_fuse(
    text_results: list[dict[str, Any]],
    vector_results: list[dict[str, Any]],
    *,
    text_weight: float = 0.5,
    vector_weight: float = 0.5,
    top_k: int | None = None,
    id_key: str = "id",
) -> list[dict[str, Any]]:
    """Fuse text + vector search results using Reciprocal Rank Fusion.

    Args:
        text_results: Results from FTS5 text search
        vector_results: Results from vector similarity search
        text_weight: Weight for text rank contribution (default 0.5)
        vector_weight: Weight for vector rank contribution (default 0.5)
        top_k: Number of results to return (default: all)
        id_key: Dict key for unique ID

    Returns:
        Ranked, deduped list with fused scores
    """
    fused: dict[str, tuple[dict[str, Any], float]] = {}

    # Assign RRF scores from text ranks
    for rank, item in enumerate(text_results):
        item_id = str(item.get(id_key, f"t{rank}"))
        rrf_score = text_weight * (1.0 / (RRF_K + rank + 1))
        fused[item_id] = (item, rrf_score)
        item["textRank"] = rank + 1
        item["vectorRank"] = None
        item["hybridScore"] = rrf_score

    # Assign RRF scores from vector ranks
    for rank, item in enumerate(vector_results):
        item_id = str(item.get(id_key, f"v{rank}"))
        rrf_score = vector_weight * (1.0 / (RRF_K + rank + 1))
        if item_id in fused:
            existing_item, existing_score = fused[item_id]
            fused[item_id] = (item, existing_score + rrf_score)
            item["textRank"] = existing_item.get("textRank")
            item["vectorRank"] = rank + 1
            item["hybridScore"] = existing_score + rrf_score
        else:
            fused[item_id] = (item, rrf_score)
            item["textRank"] = None
            item["vectorRank"] = rank + 1
            item["hybridScore"] = rrf_score

    # Sort by fused score descending
    sorted_items = sorted(fused.values(), key=lambda x: x[1], reverse=True)

    # Normalize scores to [0, 1]
    if sorted_items:
        max_score = max(s for _, s in sorted_items)
        if max_score > 0:
            for item, score in sorted_items:
                item["score"] = score / max_score
                item["hybridScore"] = score / max_score

    result = [item for item, _ in sorted_items]
    if top_k and top_k < len(result):
        result = result[:top_k]
    return result


# ── Score normalization ────────────────────────────────────────────────────


def normalize_score(score: float, min_score: float = 0.0, max_score: float = 1.0) -> float:
    """Clamp score to [0, 1] range."""
    if max_score <= min_score:
        return max(0.0, min(1.0, score))
    return max(0.0, min(1.0, (score - min_score) / (max_score - min_score)))


# ── Hybrid search aggregates ───────────────────────────────────────────────


def hybrid_search(
    text_results: list[dict[str, Any]],
    vector_results: list[dict[str, Any]],
    *,
    text_weight: float = 0.5,
    vector_weight: float = 0.5,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Convenience hybrid search — RRF fuse with defaults.

    This is the primary entry point for the recall pipeline.
    """
    return rrf_fuse(
        text_results,
        vector_results,
        text_weight=text_weight,
        vector_weight=vector_weight,
        top_k=top_k,
    )
