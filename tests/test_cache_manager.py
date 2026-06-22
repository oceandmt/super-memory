"""Tests for cache manager."""
from __future__ import annotations
import tempfile, os
from super_memory.cache.manager import ActivationCache, get_cache_manager

def test_invalidate():
    class FakeStore:
        def connect(self):
            class Conn:
                def execute(self, q, p=None):
                    pass
                def fetchone(self):
                    return None
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    pass
                def commit(self):
                    pass
            return Conn()
    cache = ActivationCache(FakeStore())
    cache._cache = {"n1": 0.8, "_timestamp": 100}
    cache.invalidate()
    assert cache._cache == {}
