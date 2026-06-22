"""Tests for preference_detector — user preference learning."""
from __future__ import annotations

import pytest
from super_memory.preference_detector import (
    PreferenceDetector, PreferenceConfig, DetectedPreference, PreferenceProfile,
)


class TestPreferenceDetector:
    def test_analyze_tech(self):
        pd = PreferenceDetector(PreferenceConfig(min_samples=1))
        signals = pd.analyze("We use Python with Django and PostgreSQL", "preference")
        assert "tech:python" in signals
        assert "tech:django" in signals
        assert "tech:postgresql" in signals

    def test_analyze_topic(self):
        pd = PreferenceDetector(PreferenceConfig(min_samples=1))
        signals = pd.analyze("Building a machine learning model with deep learning")
        assert "topic:machine learning" in signals or "topic:deep learning" in signals

    def test_analyze_empty(self):
        pd = PreferenceDetector(PreferenceConfig(min_samples=1))
        signals = pd.analyze("")
        assert signals == {}

    def test_build_profile(self):
        pd = PreferenceDetector(PreferenceConfig(min_samples=1))
        pd.analyze("We use Python with Django and PostgreSQL", "preference")
        pd.analyze("Deploying to AWS EKS with Kubernetes and Docker", "workflow")
        profile = pd.build_profile("user-1")
        assert isinstance(profile, PreferenceProfile)
        assert profile.user_id == "user-1"
        assert profile.memories_analyzed == 2
        assert len(profile.preferences) > 0

    def test_get_relevance_boost(self):
        pd = PreferenceDetector(PreferenceConfig(min_samples=1))
        pd.analyze("We use Python and Django for backend", "preference")
        pd.build_profile("user-1")
        boost = pd.get_relevance_boost("python code with django")
        assert boost > 1.0, f"expected >1.0, got {boost}"
        boost_low = pd.get_relevance_boost("gardening tips")
        assert boost_low >= 1.0

    def test_reset(self):
        pd = PreferenceDetector(PreferenceConfig(min_samples=1))
        pd.analyze("We use Python", "preference")
        assert pd._total_analyzed == 1
        pd.reset()
        assert pd._total_analyzed == 0
        assert len(pd._profile.preferences) == 0

    def test_disabled(self):
        pd = PreferenceDetector(PreferenceConfig(enabled=False))
        signals = pd.analyze("We use Python", "preference")
        assert signals == {}

    def test_get_summary(self):
        pd = PreferenceDetector(PreferenceConfig(min_samples=1))
        pd.analyze("We use Python and Django", "preference")
        summary = pd.get_summary()
        assert "memories_analyzed" in summary
        assert summary["memories_analyzed"] == 1

    def test_min_samples_threshold(self):
        pd = PreferenceDetector(PreferenceConfig(min_samples=10))
        pd.analyze("We use Python", "preference")
        boost = pd.get_relevance_boost("python")
        assert boost == 1.0  # Not enough samples yet
