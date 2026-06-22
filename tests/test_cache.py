"""Tests for cache module."""
from __future__ import annotations
from super_memory.cache.selector import select_warm_activations

def test_noop_no_query():
    assert select_warm_activations(None, {}) == {}

def test_returns_all_when_small():
    # No embedding available => returns top-k by activation level
    cached = {"n1": 0.8, "n2": 0.2}
    r = select_warm_activations([], cached, top_k=5)
    assert len(r) == 2

def test_truncates_by_top_k():
    cached = {f"n{i}": 0.1 * i for i in range(1, 11)}
    r = select_warm_activations([], cached, top_k=3)
    assert len(r) == 3

def test_empty_cached():
    assert select_warm_activations(None, {}) == {}
