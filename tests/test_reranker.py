"""Tests for reranker — hybrid BM25 + semantic + CrossEncoder fusion."""
from __future__ import annotations

import pytest
from super_memory.reranker import (
    RerankerConfig, FusedResult, fusion_rerank,
    bm25_lexical_score, reranker_available,
)


class TestBm25LexicalScore:
    def test_basic_match(self):
        score = bm25_lexical_score("python kubernetes", "deploy python app to kubernetes")
        assert score > 0, f"expected >0, got {score}"

    def test_no_match(self):
        score = bm25_lexical_score("python", "gardening tips for roses")
        assert score == 0.0

    def test_empty_input(self):
        assert bm25_lexical_score("", "content") == 0.0
        assert bm25_lexical_score("query", "") == 0.0

    def test_partial_match(self):
        score = bm25_lexical_score("python django postgres", "python is a language")
        assert score > 0, f"expected >0 for partial match, got {score}"


class TestFusionRerank:
    def test_empty_candidates(self):
        results = fusion_rerank("test", [])
        assert results == []

    def test_bm25_only_rerank(self):
        cfg = RerankerConfig(bm25_weight=1.0, semantic_weight=0.0, crossencoder_weight=0.0)
        candidates = [
            {"neuron_id": "n1", "content": "python deployment with kubernetes"},
            {"neuron_id": "n2", "content": "gardening tips for roses"},
        ]
        results = fusion_rerank("deploy python kubernetes", candidates, cfg)
        assert len(results) >= 1
        assert results[0].neuron_id == "n1"

    def test_score_threshold(self):
        cfg = RerankerConfig(bm25_weight=1.0, semantic_weight=0.0, crossencoder_weight=0.0, min_score_threshold=0.9)
        candidates = [
            {"neuron_id": "n1", "content": "about python"},
        ]
        results = fusion_rerank("quantum physics", candidates, cfg)
        assert len(results) == 0

    def test_result_type(self):
        cfg = RerankerConfig(bm25_weight=1.0, semantic_weight=0.0, crossencoder_weight=0.0)
        results = fusion_rerank("python", [{"neuron_id": "n1", "content": "python code"}], cfg)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, FusedResult)
        assert r.neuron_id == "n1"
        assert 0 <= r.score <= 1


class TestRerankerAvailable:
    def test_reranker_available(self):
        # Should return False without optional deps
        assert isinstance(reranker_available(), bool)
