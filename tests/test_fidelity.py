"""Tests for fidelity — essence extraction and layer classification."""
from __future__ import annotations

import pytest
from super_memory.fidelity import (
    extract_essence, classify_fidelity_layer,
    FIDELITY_VERBATIM, FIDELITY_DETAIL, FIDELITY_SUMMARY,
    FIDELITY_GIST, FIDELITY_ESSENCE,
)


class TestExtractEssence:
    def test_decision_content(self):
        content = "We decided to migrate from PostgreSQL to CockroachDB for better horizontal scaling. The migration took 3 weeks and required updating 47 microservices. Key benefits include multi-region deployment and automatic failover."
        essence = extract_essence(content)
        assert len(essence) > 0
        # Should capture the core: migration decision or its benefit
        has_core = any(w in essence.lower() for w in ["decided", "migrate", "migration", "benefit", "benefits"])
        assert has_core, f"essence missing core: {essence}"

    def test_short_content(self):
        essence = extract_essence("Hello world")
        assert essence == ""

    def test_empty_content(self):
        assert extract_essence("") == ""

    def test_single_sentence(self):
        text = "We deployed v2.3 to production using ArgoCD."
        essence = extract_essence(text)
        assert len(essence) > 0

    def test_multi_sentence_picks_best(self):
        content = "The weather was nice today. We decided to adopt CockroachDB for production. Lunch was good."
        essence = extract_essence(content)
        # Should pick the substantive sentence
        assert "CockroachDB" in essence or "adopt" in essence.lower()

    def test_boilerplate_excluded(self):
        content = "Hello! Thanks for the update. We deployed the fix to production. Best regards, Team."
        essence = extract_essence(content)
        assert len(essence) > 0
        assert "deployed" in essence.lower()


class TestClassifyFidelityLayer:
    def test_verbatim_markdown(self):
        content = "# Title\n\n**bold** and `code`"
        assert classify_fidelity_layer(content) == FIDELITY_VERBATIM

    def test_verbatim_code(self):
        content = "def hello():\n    return 'world'"
        assert classify_fidelity_layer(content) == FIDELITY_VERBATIM

    def test_detail(self):
        content = "We migrated from PostgreSQL 15 to CockroachDB v23.1 on AWS EKS. " * 3
        assert classify_fidelity_layer(content) == FIDELITY_DETAIL

    def test_summary(self):
        content = "We migrated to CockroachDB for horizontal scaling. It took 3 weeks."
        assert classify_fidelity_layer(content) == FIDELITY_SUMMARY

    def test_gist(self):
        content = "Migrated to CockroachDB for scaling."
        assert classify_fidelity_layer(content) in (FIDELITY_GIST, FIDELITY_ESSENCE)

    def test_essence(self):
        assert classify_fidelity_layer("Migrated.") == FIDELITY_ESSENCE

    def test_empty(self):
        assert classify_fidelity_layer("") == FIDELITY_ESSENCE
