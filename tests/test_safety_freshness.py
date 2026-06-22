"""Tests for safety.freshness module."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from super_memory.safety.freshness import evaluate_freshness, FreshnessLevel

def test_fresh():
    r = evaluate_freshness(datetime.now(timezone.utc))
    assert r.level == FreshnessLevel.FRESH
    assert r.score >= 0.9

def test_stale():
    r = evaluate_freshness(datetime.now(timezone.utc) - timedelta(days=200))
    assert r.level == FreshnessLevel.STALE

def test_ancient():
    r = evaluate_freshness(datetime.now(timezone.utc) - timedelta(days=400))
    assert r.level == FreshnessLevel.ANCIENT

def test_aging():
    r = evaluate_freshness(datetime.now(timezone.utc) - timedelta(days=45))
    assert r.level == FreshnessLevel.AGING

def test_warning_on_old():
    r = evaluate_freshness(datetime.now(timezone.utc) - timedelta(days=200))
    assert r.warning is not None
    assert r.should_verify
