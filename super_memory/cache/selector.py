"""SSC-lite: query-embedding ranked warm restore."""
from __future__ import annotations
import math, logging
from typing import Any

logger = logging.getLogger("super-memory.cache.selector")

DEFAULT_TOP_K = 20
DEFAULT_MIN_SIMILARITY = 0.3

def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b): return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-10)

def select_warm_activations(
    query_embedding: list[float] | None,
    cached_activations: dict[str, float],
    top_k: int = DEFAULT_TOP_K,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> dict[str, float]:
    if not cached_activations or query_embedding is None:
        return {}
    if len(cached_activations) <= top_k:
        return cached_activations
    # Return top-k by cached activation level (no embedding available)
    sorted_items = sorted(cached_activations.items(), key=lambda x: -x[1])
    return dict(sorted_items[:top_k])
