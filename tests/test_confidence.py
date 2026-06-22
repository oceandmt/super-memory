"""Tests for confidence — unified metacognitive confidence scoring."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from super_memory.confidence import (
    ConfidenceScore, ConfidenceWeights, compute_confidence, FIDELITY_LAYER_SCORES,
)


class TestComputeConfidence:
    def test_default_scores(self):
        cs = compute_confidence()
        assert isinstance(cs, ConfidenceScore)
        assert 0 <= cs.overall <= 1
        assert 0 <= cs.retrieval <= 1
        assert 0 <= cs.content_quality <= 1
        assert 0 <= cs.fidelity <= 1
        assert 0 <= cs.freshness <= 1

    def test_high_confidence(self):
        cs = compute_confidence(
            retrieval_score=0.95,
            sufficiency_confidence=0.9,
            quality_score=9.5,
            fidelity_layer="verbatim",
            created_at=datetime.now(timezone.utc),
        )
        assert cs.overall > 0.8, f"expected >0.8, got {cs.overall}"

    def test_low_confidence(self):
        cs = compute_confidence(
            retrieval_score=0.1,
            sufficiency_confidence=0.1,
            quality_score=1.0,
            fidelity_layer="essence",
            created_at=datetime.now(timezone.utc) - timedelta(days=365),
        )
        assert cs.overall < 0.5, f"expected <0.5, got {cs.overall}"

    def test_familiarity_penalty(self):
        cs = compute_confidence(
            retrieval_score=0.8,
            is_familiarity_fallback=True,
        )
        assert cs.familiarity_penalty == -0.3
        assert cs.overall < 0.8  # Penalized

    def test_freshness_decay(self):
        old = datetime.now(timezone.utc) - timedelta(days=90)
        cs_old = compute_confidence(created_at=old)
        cs_fresh = compute_confidence(created_at=datetime.now(timezone.utc))
        assert cs_old.freshness < cs_fresh.freshness, "older should have lower freshness"

    def test_fidelity_verbatim(self):
        cs = compute_confidence(fidelity_layer="verbatim")
        assert cs.fidelity == 1.0

    def test_fidelity_essence(self):
        cs = compute_confidence(fidelity_layer="essence")
        assert cs.fidelity == 0.3

    def test_unknown_fidelity_defaults(self):
        cs = compute_confidence(fidelity_layer="unknown")
        assert cs.fidelity == 0.5

    def test_custom_weights(self):
        w = ConfidenceWeights(retrieval=0.5, content_quality=0.3, fidelity=0.1, freshness=0.1)
        cs = compute_confidence(
            retrieval_score=1.0, quality_score=10.0, fidelity_layer="verbatim",
            weights=w,
        )
        assert cs.overall > 0.5

    def test_naive_datetime(self):
        naive = datetime(2024, 1, 1)
        cs = compute_confidence(created_at=naive)
        assert cs.freshness < 0.6  # More than a year old, should be decayed

    def test_extra_signals(self):
        cs = compute_confidence(extra_signals={"custom_metric": 0.85})
        assert "custom_metric" in cs.components
        assert cs.components["custom_metric"] == 0.85

    def test_components_dict(self):
        cs = compute_confidence(retrieval_score=0.75, quality_score=7.0)
        assert "retrieval_score" in cs.components
        assert "quality_score" in cs.components
        assert "age_days" in cs.components
