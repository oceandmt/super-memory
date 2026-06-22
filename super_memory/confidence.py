"""Unified metacognitive confidence scoring for recall results.

Aggregates multiple quality signals (retrieval strength, content quality,
fidelity layer, freshness, familiarity) into a single 0-1 confidence score
that callers use to gauge how much to trust a recall result.

Usage::

    cs = compute_confidence(
        retrieval_score=0.82,
        quality_score=7.5,
        fidelity_layer="verbatim",
        created_at=memory_created_at,
    )
    print(f"Confidence: {cs.overall:.2f}")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "ConfidenceScore",
    "ConfidenceWeights",
    "compute_confidence",
    "FIDELITY_LAYER_SCORES",
]

logger = logging.getLogger("super-memory.confidence")

# Fidelity layer → numeric score mapping
# verbatim = exact text preserved, detail = rich but not exact,
# summary = condensed, gist = approximate meaning, essence = single sentence
FIDELITY_LAYER_SCORES: dict[str, float] = {
    "verbatim": 1.0,
    "detail": 0.7,
    "summary": 0.5,
    "gist": 0.4,
    "essence": 0.3,
}


@dataclass(frozen=True)
class ConfidenceScore:
    """Unified confidence assessment for a recall result.

    Attributes:
        overall: Single 0-1 score — primary output for consumers.
        retrieval: Retrieval pipeline strength (activation + sufficiency).
        content_quality: Normalized quality score (0-1).
        fidelity: Encoding fidelity (verbatim=1.0 down to essence=0.3).
        freshness: Age-based decay (1.0 fresh, decays over time).
        familiarity_penalty: 0.0 for real recall, negative for familiarity fallback.
        components: All raw signal values for transparency/debugging.
    """
    overall: float
    retrieval: float
    content_quality: float
    fidelity: float
    freshness: float
    familiarity_penalty: float = 0.0
    components: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfidenceWeights:
    """Configurable weights for confidence aggregation.

    Defaults balanced for general-purpose recall. Adjust per use-case.
    """
    retrieval: float = 0.35
    content_quality: float = 0.25
    fidelity: float = 0.20
    freshness: float = 0.20


def compute_confidence(
    retrieval_score: float = 0.5,
    sufficiency_confidence: float = 0.5,
    quality_score: float = 5.0,
    fidelity_layer: str = "detail",
    created_at: datetime | None = None,
    is_familiarity_fallback: bool = False,
    weights: ConfidenceWeights | None = None,
    extra_signals: dict[str, Any] | None = None,
) -> ConfidenceScore:
    """Compute unified confidence from multiple quality signals.

    Args:
        retrieval_score: Fiber/neuron score from retrieval pipeline (0-1 typical).
        sufficiency_confidence: Sufficiency gate confidence (0-1).
        quality_score: Content quality score (0-10 scale, from quality_scorer).
        fidelity_layer: Encoding fidelity level:
            'verbatim' (1.0), 'detail' (0.7), 'summary' (0.5),
            'gist' (0.4), 'essence' (0.3).
        created_at: When the memory was created (for freshness decay).
        is_familiarity_fallback: Whether this is a familiarity guess, not real recall.
        weights: Optional custom weights (defaults used if None).
        extra_signals: Additional raw signals to include in components dict.

    Returns:
        ConfidenceScore with overall and per-dimension scores.
    """
    w = weights or ConfidenceWeights()

    # 1. Retrieval dimension: blend pipeline score with sufficiency
    retrieval = min(1.0, max(0.0, retrieval_score * 0.6 + sufficiency_confidence * 0.4))

    # 2. Content quality: normalize 0-10 → 0-1
    content_quality = min(1.0, max(0.0, quality_score / 10.0))

    # 3. Fidelity: map layer name to score
    fidelity = FIDELITY_LAYER_SCORES.get(fidelity_layer, 0.5)

    # 4. Freshness: sigmoid decay based on age in days
    now = datetime.now(timezone.utc)
    if created_at is not None:
        # Ensure naive datetime interpreted as UTC
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
        # Half-life ~30 days: freshness = 1 / (1 + age/30)
        freshness = 1.0 / (1.0 + age_days / 30.0)
    else:
        freshness = 0.5  # Unknown age, neutral

    # 5. Familiarity penalty
    familiarity_penalty = -0.3 if is_familiarity_fallback else 0.0

    # Weighted sum with penalty applied outside weights
    overall = (
        w.retrieval * retrieval
        + w.content_quality * content_quality
        + w.fidelity * fidelity
        + w.freshness * freshness
        + familiarity_penalty
    )
    overall = min(1.0, max(0.0, overall))

    # Collect all components for transparency
    age_days_val: float = -1.0
    if created_at is not None:
        age_days_val = round((now - created_at).total_seconds() / 86400.0, 1)

    components: dict[str, float] = {
        "retrieval_score": round(retrieval_score, 4),
        "sufficiency_confidence": round(sufficiency_confidence, 4),
        "quality_score": round(quality_score, 2),
        "fidelity_layer_value": round(fidelity, 4),
        "age_days": age_days_val,
        "is_familiarity_fallback": 1.0 if is_familiarity_fallback else 0.0,
    }
    if extra_signals:
        for k, v in extra_signals.items():
            if isinstance(v, (int, float)):
                components[k] = round(float(v), 4)

    return ConfidenceScore(
        overall=round(overall, 4),
        retrieval=round(retrieval, 4),
        content_quality=round(content_quality, 4),
        fidelity=round(fidelity, 4),
        freshness=round(freshness, 4),
        familiarity_penalty=round(familiarity_penalty, 4),
        components=components,
    )

# ── Safe wrapper ─────────────────────────────────────────────────────────────

def compute_confidence_safe(*args, **kwargs) -> dict:
    """Safe wrapper for compute_confidence with error handling."""
    try:
        result = compute_confidence(*args, **kwargs)
        return {
            "overall": result.overall,
            "retrieval": result.retrieval,
            "sufficiency": result.sufficiency,
            "freshness": result.freshness,
            "fidelity": result.fidelity,
            "familiarity": result.familiarity,
        }
    except Exception as e:
        logger.error("compute_confidence failed: %s", e, exc_info=True)
        return {"overall": 0.0, "error": str(e)}
