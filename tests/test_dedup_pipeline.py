"""Tests for dedup pipeline."""
from __future__ import annotations
from super_memory.dedup.config import DedupConfig
from super_memory.dedup.pipeline import DedupPipeline, DEDUP_SYSTEM_PROMPT, DEDUP_USER_PROMPT

def test_config_defaults():
    cfg = DedupConfig()
    assert cfg.enabled
    assert cfg.simhash_threshold == 7
    assert cfg.embedding_threshold == 0.85

def test_config_disable():
    cfg = DedupConfig(enabled=False)
    assert not cfg.enabled

def test_config_from_dict():
    cfg = DedupConfig.from_dict({"simhash_threshold": 3, "embedding_threshold": 0.9})
    assert cfg.simhash_threshold == 3
    assert cfg.embedding_threshold == 0.9

def test_prompt_templates_not_empty():
    assert len(DEDUP_SYSTEM_PROMPT) > 50
    assert "{content_a}" in DEDUP_USER_PROMPT
    assert "{content_b}" in DEDUP_USER_PROMPT

def test_pipeline_disabled():
    dp = DedupPipeline(DedupConfig(enabled=False), None)
    r = dp.check_duplicate("test content")
    assert not r.is_duplicate
    assert r.reason == "dedup disabled"
