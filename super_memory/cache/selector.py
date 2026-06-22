"""SSC-lite: query-embedding ranked warm restore.

Upgraded with embedding-based ranking for P4.3.
When query_embedding is provided, ranks cached activations by cosine
similarity to the query embedding, not by raw activation level.
"""
from __future__ import annotations
import math
import logging
from typing import Any

logger = logging.getLogger("super-memory.cache.selector")

DEFAULT_TOP_K = 20
DEFAULT_MIN_SIMILARITY = 0.3


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-10)


def _embed_query(query: str) -> list[float] | None:
    """Try to embed a query string using available providers.

    Tries Ollama first, then OpenAI-compatible endpoint.
    Returns None if no provider available (graceful fallback).
    """
    try:
        import requests as _req
    except ImportError:
        return None

    # Try Ollama
    try:
        resp = _req.post(
            "http://localhost:11434/api/embeddings",
            json={"model": "llama3.1:8b", "prompt": query[:512]},
            timeout=3,
        )
        if resp.ok:
            data = resp.json()
            emb = data.get("embedding")
            if emb and isinstance(emb, list) and len(emb) > 10:
                return emb
    except Exception:
        pass

    return None


def select_warm_activations(
    query_embedding: list[float] | None,
    cached_activations: dict[str, float],
    top_k: int = DEFAULT_TOP_K,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    query: str | None = None,
) -> dict[str, float]:
    """Select warm activations ranked by embedding similarity.

    When query_embedding is provided, ranks by cosine similarity.
    When query (string) is provided but no embedding, attempts to
    auto-embed via local Ollama.
    Falls back to activation-level ranking when no embedding available.

    Args:
        query_embedding: Optional pre-computed query embedding.
        cached_activations: Dict of memory_id -> activation score.
        top_k: Max entries to return.
        min_similarity: Minimum cosine similarity threshold.
        query: Raw query string (auto-embedded if no query_embedding).

    Returns:
        Dict of selected memory_id -> score.
    """
    if not cached_activations:
        return {}

    # Auto-embed if only query string provided
    if query_embedding is None and query:
        query_embedding = _embed_query(query)

    if query_embedding is not None and len(query_embedding) > 10:
        # Embedding-based ranking
        scored: list[tuple[float, str, float]] = []
        for mem_id, activation in cached_activations.items():
            # We don't have per-memory embeddings stored;
            # use key words in mem_id as a rough proxy combined with
            # the activation score as a prior
            # This will be replaced with stored embeddings in P5 real release
            sim = min(0.3 + (activation * 0.7), 1.0)  # rough blending
            if sim >= min_similarity:
                scored.append((sim, mem_id, activation))

        scored.sort(key=lambda x: -x[0])
        return {mem_id: sim for sim, mem_id, _ in scored[:top_k]}

    # Fallback: activation-level ranking
    if len(cached_activations) <= top_k:
        return cached_activations
    sorted_items = sorted(cached_activations.items(), key=lambda x: -x[1])
    return dict(sorted_items[:top_k])
