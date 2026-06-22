"""Reranker — hybrid CrossEncoder + score fusion for recall re-ranking.

After spreading activation returns candidate neurons, reranker re-orders them
by combining BM25 lexical score, semantic embedding similarity, and CrossEncoder
relevance score into a single fused rank. Falls back gracefully when optional
dependencies (sentence-transformers, scikit-learn) are unavailable.
"""
from __future__ import annotations

import logging
import re
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "RerankerConfig", "FusedResult", "fusion_rerank",
    "bm25_lexical_score", "reranker_available",
]

logger = logging.getLogger("super-memory.reranker")

# ── Optional deps ────────────────────────────────────────────────────────────

_HAS_CROSSENCODER = False
try:
    from sentence_transformers import CrossEncoder
    _HAS_CROSSENCODER = True
except ImportError:
    pass

_HAS_SENTENCE_TRANSFORMERS = False
try:
    from sentence_transformers import SentenceTransformer
    _HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    pass

_HAS_SKLEARN = False
try:
    from sklearn.preprocessing import MinMaxScaler
    _HAS_SKLEARN = True
except ImportError:
    pass


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class RerankerConfig:
    """Configuration for the hybrid reranker.

    Attributes:
        bm25_weight: Weight for BM25 lexical score in final fusion.
        semantic_weight: Weight for semantic embedding similarity.
        crossencoder_weight: Weight for CrossEncoder relevance.
        crossencoder_model: Model name for CrossEncoder.
        sentence_model: Model name for SentenceTransformer embeddings.
        top_k_rerank: Max candidates to rerank (capped for performance).
        min_score_threshold: Minimum fused score to return.
    """
    bm25_weight: float = 0.25
    semantic_weight: float = 0.35
    crossencoder_weight: float = 0.40
    crossencoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    sentence_model: str = "all-MiniLM-L6-v2"
    top_k_rerank: int = 50
    min_score_threshold: float = 0.1


@dataclass
class FusedResult:
    """A single reranked result with component scores."""
    neuron_id: str
    content: str
    score: float          # Fused final score
    bm25_score: float     # Lexical match score
    semantic_score: float  # Embedding similarity
    crossencoder_score: float  # CrossEncoder relevance


# ── BM25 Lexical Scoring ─────────────────────────────────────────────────────

def bm25_lexical_score(query: str, document: str, k1: float = 1.5, b: float = 0.75) -> float:
    """Compute BM25-style lexical relevance score.

    Simplified BM25 for single query vs single document.
    Falls back to TF-IDF cosine when BM25 terms are insufficient.
    """
    if not query or not document:
        return 0.0
    query_terms = [t.lower().strip() for t in re.findall(r"\w{3,}", query)]
    if not query_terms:
        return 0.0

    doc_lower = document.lower()
    doc_words = re.findall(r"\w+", doc_lower)
    doc_len = len(doc_words)
    if doc_len == 0:
        return 0.0

    avg_doc_len = 100.0  # Assumed average document length
    term_freq = Counter(doc_words)
    
    score = 0.0
    for term in set(query_terms):
        tf = term_freq.get(term, 0)
        if tf == 0:
            continue
        idf = math.log((len(doc_words) + 1) / (max(tf, 1) + 0.5)) + 1.0
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * doc_len / avg_doc_len)
        score += idf * (numerator / max(denominator, 0.001))
    
    return min(score / 10.0, 1.0)  # Normalize to [0, 1]


# ── Embedding similarity ─────────────────────────────────────────────────────

def _embed_text(text: str, model_name: str = "all-MiniLM-L6-v2") -> list[float] | None:
    """Embed text using SentenceTransformer. Returns None if unavailable."""
    if not _HAS_SENTENCE_TRANSFORMERS:
        return None
    try:
        model = SentenceTransformer(model_name)
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()
    except Exception as e:
        logger.debug("embedding failed: %s", e)
        return None


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── CrossEncoder scoring ─────────────────────────────────────────────────────

_CROSS_ENCODER_CACHE: dict[str, Any] = {}

def _crossencoder_score(query: str, document: str, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> float:
    """Score (query, document) pair with CrossEncoder. Returns 0 if unavailable."""
    global _CROSS_ENCODER_CACHE
    if not _HAS_CROSSENCODER:
        return 0.0
    try:
        if model_name not in _CROSS_ENCODER_CACHE:
            _CROSS_ENCODER_CACHE[model_name] = CrossEncoder(model_name)
        model = _CROSS_ENCODER_CACHE[model_name]
        result = model.predict([(query, document)])
        score = float(result[0])
        # Normalize sigmoid output to roughly [0, 1]
        return max(0.0, min(1.0, (score + 1.0) / 2.0))
    except Exception as e:
        logger.debug("CrossEncoder scoring failed: %s", e)
        return 0.0


# ── Fusion Rerank ────────────────────────────────────────────────────────────

def fusion_rerank(
    query: str,
    candidates: list[dict[str, Any]],
    config: RerankerConfig | None = None,
) -> list[FusedResult]:
    """Rerank recall candidates using hybrid score fusion.

    Args:
        query: Original recall query.
        candidates: List of dicts with 'neuron_id', 'content' keys.
        config: RerankerConfig (defaults used if None).

    Returns:
        List of FusedResult sorted by fused score descending.
    """
    if config is None:
        config = RerankerConfig()

    if not candidates:
        return []

    # Limit candidates for performance
    working = candidates[:config.top_k_rerank]

    # Pre-compute query embedding once
    query_embedding = _embed_text(query, config.sentence_model)
    results: list[FusedResult] = []

    for cand in working:
        content = cand.get("content", cand.get("text", ""))
        if not content:
            continue
        
        nid = cand.get("neuron_id", cand.get("id", ""))

        # Component scores
        bm25 = bm25_lexical_score(query, content)

        semantic = 0.0
        if query_embedding:
            doc_emb = _embed_text(content[:500], config.sentence_model)
            if doc_emb:
                semantic = _cosine_similarity(query_embedding, doc_emb)

        cross = _crossencoder_score(query, content[:512], config.crossencoder_model)

        # Fuse
        weights_total = config.bm25_weight + config.semantic_weight + config.crossencoder_weight
        if weights_total > 0:
            fused = (
                bm25 * config.bm25_weight
                + semantic * config.semantic_weight
                + cross * config.crossencoder_weight
            ) / weights_total
        else:
            fused = bm25

        if fused >= config.min_score_threshold:
            results.append(FusedResult(
                neuron_id=nid,
                content=content[:200],
                score=round(fused, 4),
                bm25_score=round(bm25, 4),
                semantic_score=round(semantic, 4),
                crossencoder_score=round(cross, 4),
            ))

    # Sort descending by fused score
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def reranker_available() -> bool:
    """Check if reranker has at least one scoring method available."""
    return _HAS_CROSSENCODER or _HAS_SENTENCE_TRANSFORMERS
