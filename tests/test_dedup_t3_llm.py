"""Tests for Tier 3 LLM-based dedup."""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from super_memory.dedup.pipeline import DedupPipeline, DedupResult
from super_memory.dedup.config import DedupConfig


class _MockStore:
    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, *params):
        class _Cursor:
            def fetchall(self):
                return []
            def fetchone(self):
                return [0]
        return _Cursor()


@pytest.fixture
def pipeline():
    cfg = DedupConfig(enabled=True, llm_enabled=True)
    store = _MockStore()
    return DedupPipeline(cfg, store)


def test_t3_llm_skipped_when_disabled():
    """T3 should be skipped when llm_enabled=False."""
    cfg = DedupConfig(enabled=True, llm_enabled=False)
    store = _MockStore()
    p = DedupPipeline(cfg, store)
    result = p._tier3_llm("test", [{"id": "1", "content": "test content"}])
    assert result is None


def test_t3_llm_skipped_when_no_candidates():
    """T3 should return None when no candidates provided."""
    cfg = DedupConfig(enabled=True, llm_enabled=True)
    p = DedupPipeline(cfg, None)
    result = p._tier3_llm("test", [])
    assert result is None


def test_t3_llm_duplicate_response():
    """T3 should return DedupResult(is_duplicate=True) when LLM says DUPLICATE."""
    cfg = DedupConfig(enabled=True, llm_enabled=True)
    store = _MockStore()
    p = DedupPipeline(cfg, store)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "DUPLICATE\nBoth memories describe the same API timeout fix."}}]
    }

    with patch("requests.post", return_value=mock_response):
        result = p._tier3_llm("fix api timeout", [{"id": "m1", "content": "fixed api timeout bug"}])

    assert result is not None
    assert result.is_duplicate is True
    assert result.tier == 3


def test_t3_llm_distinct_response():
    """T3 should return DedupResult(is_duplicate=False) when LLM says DISTINCT."""
    cfg = DedupConfig(enabled=True, llm_enabled=True)
    store = _MockStore()
    p = DedupPipeline(cfg, store)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "DISTINCT\nThese describe different features."}}]
    }

    with patch("requests.post", return_value=mock_response):
        result = p._tier3_llm("add login page", [{"id": "m2", "content": "fix navbar css"}])

    assert result is not None
    assert result.is_duplicate is False
    assert result.tier == 3


def test_t3_llm_uncertain_response():
    """T3 should return None (defer) when LLM says UNCERTAIN."""
    cfg = DedupConfig(enabled=True, llm_enabled=True)
    store = _MockStore()
    p = DedupPipeline(cfg, store)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "UNCERTAIN\nThe contexts are too different to judge."}}]
    }

    with patch("requests.post", return_value=mock_response):
        result = p._tier3_llm("random text", [{"id": "m3", "content": "some other text"}])

    # UNCERTAIN defers — result is None, caller falls through to no-match
    assert result is None


def test_t3_llm_connection_error():
    """T3 should fail gracefully when LLM endpoint is unreachable."""
    cfg = DedupConfig(enabled=True, llm_enabled=True)
    store = _MockStore()
    p = DedupPipeline(cfg, store)

    with patch("requests.post", side_effect=ConnectionError("connection refused")):
        result = p._tier3_llm("test content", [{"id": "m4", "content": "other content"}])

    assert result is None  # graceful fallback


def test_t3_llm_timeout():
    """T3 should fail gracefully on timeout."""
    cfg = DedupConfig(enabled=True, llm_enabled=True)
    store = _MockStore()
    p = DedupPipeline(cfg, store)

    with patch("requests.post", side_effect=TimeoutError("timed out")):
        result = p._tier3_llm("test content", [{"id": "m5", "content": "other content"}])

    assert result is None


def test_t3_llm_empty_content_candidate():
    """T3 should skip candidate with empty content."""
    cfg = DedupConfig(enabled=True, llm_enabled=True)
    store = _MockStore()
    p = DedupPipeline(cfg, store)
    result = p._tier3_llm("test", [{"id": "6", "content": ""}])
    assert result is None


def test_t3_llm_wired_into_check_duplicate():
    """Verify T3 is called from check_duplicate when enabled."""
    cfg = DedupConfig(
        enabled=True,
        simhash_threshold=0,  # aggressive - but we'll mock
        llm_enabled=True,
    )
    store = _MockStore()
    p = DedupPipeline(cfg, store)

    # Mock candidate fetch to return a candidate
    with patch.object(p, "_get_candidates", return_value=[{"id": "m1", "content": "existing memory content"}]):
        with patch.object(p, "_tier1_simhash", return_value=None):
            with patch.object(p, "_tier2_embedding", return_value=None):
                with patch.object(p, "_tier3_llm", return_value=None) as mock_t3:
                    p.check_duplicate("new content here")
                    mock_t3.assert_called_once()
