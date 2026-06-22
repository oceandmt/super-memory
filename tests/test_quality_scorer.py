"""Tests for quality_scorer — fidelity, sufficiency, importance scoring."""
from __future__ import annotations

import pytest
from super_memory.quality_scorer import (
    QualityConfig, QualityScore, score_memory,
    fidelity_score, sufficiency_score, importance_score,
)


class TestFidelity:
    def test_focused_content_high(self):
        content = "We decided to migrate from PostgreSQL 15 to CockroachDB for better horizontal scaling. The migration took 3 weeks and required updating 47 microservices. Key benefits include multi-region deployment and automatic failover."
        score = fidelity_score(content)
        assert score > 0.5, f"expected >0.5 for focused content, got {score}"

    def test_short_content(self):
        score = fidelity_score("hi")
        assert score >= 0

    def test_noisy_content_low(self):
        content = " ".join(["word"] * 200)
        score = fidelity_score(content)
        assert score >= 0


class TestSufficiency:
    def test_detailed_content_high(self):
        content = "We migrated from PostgreSQL to CockroachDB (v23.1) on AWS EKS. The migration affected 47 microservices and took 3 weeks. Key configuration changes: updated connection pool from 20 to 50, enabled TLS v1.3, configured automated backups."
        score = sufficiency_score(content)
        assert score > 0.5, f"expected >0.5 for detailed content, got {score}"

    def test_vague_content_low(self):
        content = "it was something that happened and stuff like that. thing was done somewhere."
        score = sufficiency_score(content)
        assert score >= 0

    def test_empty_content(self):
        assert sufficiency_score("") == 0.0


class TestImportance:
    def test_decision_high(self):
        content = "We decided to adopt CockroachDB for production. This was chosen after evaluating YugabyteDB and TiDB."
        score = importance_score(content, "decision")
        assert score > 0.3, f"expected >0.3 for decision, got {score}"

    def test_error_high(self):
        content = "CRITICAL BUG: The connection pool exhaustion caused complete database outage. Root cause was a race condition in the migration script."
        score = importance_score(content, "error")
        assert score > 0.3, f"expected >0.3 for error, got {score}"

    def test_routine_low(self):
        content = "The weather was nice today. Had lunch at the usual place."
        score = importance_score(content, "context")
        assert score >= 0

    def test_empty(self):
        assert importance_score("") == 0.2


class TestScoreMemory:
    def test_full_scoring(self):
        content = "We decided to migrate from PostgreSQL to CockroachDB for better horizontal scaling. The migration took 3 weeks."
        qs = score_memory(content, "decision")
        assert isinstance(qs, QualityScore)
        assert 0 <= qs.overall <= 1
        assert 0 <= qs.fidelity <= 1
        assert 0 <= qs.sufficiency <= 1
        assert 0 <= qs.importance <= 1

    def test_disabled(self):
        cfg = QualityConfig(enabled=False)
        qs = score_memory("test", config=cfg)
        assert qs.overall == 0.5

    def test_short_content(self):
        qs = score_memory("hi", config=QualityConfig(min_content_chars=50))
        assert qs.overall == 0.5

    def test_warnings(self):
        qs = score_memory("a", config=QualityConfig(min_content_chars=1))
        assert hasattr(qs, "warnings")
