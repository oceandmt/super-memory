"""Tests for cache.selector module."""
from __future__ import annotations
from super_memory.cache.selector import select_warm_activations

def test_no_cached():
    assert select_warm_activations([], {}) == {}

def test_returns_all_small():
    r = select_warm_activations([], {"a": 0.9, "b": 0.3}, top_k=5)
    assert len(r) == 2

def test_truncates():
    r = select_warm_activations([], {"a": 0.9, "b": 0.3, "c": 0.1, "d": 0.05}, top_k=2)
    assert len(r) == 2
    assert list(r.keys()) == ["a", "b"]

def test_empty_with_none():
    assert select_warm_activations(None, {}) == {}
