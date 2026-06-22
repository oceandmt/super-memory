"""Tests for dedup config."""
from __future__ import annotations
from super_memory.dedup.config import DedupConfig

def test_defaults():
    cfg = DedupConfig()
    assert cfg.enabled
    assert cfg.simhash_threshold == 7
    assert cfg.embedding_threshold == 0.85

def test_custom():
    cfg = DedupConfig(simhash_threshold=3, max_candidates=10)
    assert cfg.simhash_threshold == 3
    assert cfg.max_candidates == 10

def test_to_dict():
    cfg = DedupConfig()
    d = cfg.to_dict()
    assert d["simhash_threshold"] == 7
    assert d["enabled"] is True

def test_from_dict():
    cfg = DedupConfig.from_dict({"simhash_threshold": 5})
    assert cfg.simhash_threshold == 5

def test_from_dict_empty():
    cfg = DedupConfig.from_dict({})
    assert cfg.enabled
