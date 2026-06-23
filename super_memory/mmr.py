"""Maximum Marginal Relevance (MMR) diversity reranker for search results.

Matches OpenClaw memory-core MMR implementation:
- Balances relevance (score) with diversity (novelty against already-selected)
- Configurable lambda parameter (0 = pure diversity, 1 = pure relevance)
- Cosine similarity for novelty measurement
"""

from __future__ import annotations

import math
import re
from typing import Any


# ── Tokenizer ───────────────────────────────────────────────────────────────


def _tokenize(text: str) -> set[str]:
    """Simple word-level tokenizer for similarity computation."""
    return set(re.findall(r'\w+', text.lower()))


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity between two texts (0.0 = different, 1.0 = identical)."""
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / max(len(union), 1)


# ── MMR Reranker ────────────────────────────────────────────────────────────


def mmr_rerank(
    items: list[dict[str, Any]],
    query: str | None = None,
    *,
    lambda_param: float = 0.7,
    top_k: int | None = None,
    score_key: str = "score",
    text_key: str = "snippet",
    id_key: str = "id",
) -> list[dict[str, Any]]:
    """Rerank search results using Maximum Marginal Relevance.

    Args:
        items: List of search result dicts (must have score + text fields)
        query: Original query string (for relevance computation)
        lambda_param: 0.0 = pure diversity, 1.0 = pure relevance (default 0.7)
        top_k: Number of results to return (default: all)
        score_key: Dict key for score (default 'score')
        text_key: Dict key for text/snippet (default 'snippet')
        id_key: Dict key for unique ID (default 'id')

    Returns:
        Reranked list of result dicts
    """
    if not items:
        return []

    n = len(items)
    top_k = top_k or n
    if top_k >= n:
        top_k = n

    # Normalize scores to [0, 1]
    scores = [max(0.0, min(1.0, item.get(score_key, 0.0))) for item in items]

    # Precompute similarity matrix
    sim_matrix = _compute_similarity_matrix(items, text_key, id_key)

    # MMR selection loop
    selected: list[int] = []
    candidates = list(range(n))

    # Score candidates by MMR
    for _ in range(top_k):
        if not candidates:
            break

        best_idx = -1
        best_score = -float('inf')

        for i in candidates:
            # Relevance term: the item's original score
            relevance = scores[i]

            # Novelty term: max similarity to any already-selected item
            if selected:
                max_sim = max(sim_matrix[i][j] for j in selected)
            else:
                max_sim = 0.0

            # MMR score: λ * relevance - (1-λ) * max_sim
            mmr_score = lambda_param * relevance - (1.0 - lambda_param) * max_sim

            # Boost exact query match
            if query:
                text = str(items[i].get(text_key, "")).lower()
                if query.lower() in text:
                    mmr_score += 0.1

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i

        if best_idx >= 0:
            selected.append(best_idx)
            candidates.remove(best_idx)

    return [items[i] for i in selected]


def _compute_similarity_matrix(
    items: list[dict[str, Any]],
    text_key: str,
    id_key: str,
) -> list[list[float]]:
    """Compute NxN similarity matrix for items using Jaccard."""
    n = len(items)
    texts = [str(item.get(text_key, "") or "") for item in items]
    ids = [str(item.get(id_key, "")) for item in items]

    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            # Same ID = same item
            if ids[i] and ids[i] == ids[j]:
                sim = 1.0
            else:
                sim = jaccard_similarity(texts[i], texts[j])
            matrix[i][j] = sim
            matrix[j][i] = sim
    return matrix


# ── Convenience wrapper ─────────────────────────────────────────────────────


def diversify_results(
    results: list[dict[str, Any]],
    query: str,
    *,
    top_k: int | None = None,
    lambda_param: float = 0.7,
) -> list[dict[str, Any]]:
    """One-call MMR diversity reranking for search results.

    This is the primary entry point used by the recall pipeline.
    """
    return mmr_rerank(
        results,
        query,
        lambda_param=lambda_param,
        top_k=top_k,
        score_key="score",
        text_key="snippet",
        id_key="id",
    )
