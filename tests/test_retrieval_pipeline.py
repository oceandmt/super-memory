"""Tests for retrieval_pipeline — composable recall orchestration."""
from __future__ import annotations

import pytest
from super_memory.retrieval_pipeline import (
    RetrievalPipeline, RetrievalConfig, RetrievalStep,
    QueryIntent, DepthLevel, parse_query, query_expand,
    format_context, compute_result_confidence, PipelineResult,
)


class TestParseQuery:
    def test_basic_query(self):
        intent = parse_query("python deployment with kubernetes")
        assert isinstance(intent, QueryIntent)
        assert intent.depth == DepthLevel.CONTEXT

    def test_question_detection(self):
        intent = parse_query("what is the deployment strategy?")
        assert intent.is_question is True

    def test_why_question(self):
        intent = parse_query("Why did the database fail?")
        assert intent.is_question is True
        assert intent.is_causal is True

    def test_temporal_detection(self):
        intent = parse_query("what happened last week with the migration")
        assert intent.is_temporal is True

    def test_entity_extraction(self):
        intent = parse_query("CockroachDB vs PostgreSQL migration")
        assert len(intent.entities) > 0

    def test_topic_extraction(self):
        intent = parse_query("deploy python kubernetes application")
        assert "kubernetes" in intent.topics or "deploy" in intent.topics


class TestQueryExpand:
    def test_no_graph_context(self):
        expanded, terms = query_expand("python deployment", graph_context=None)
        assert expanded == "python deployment"
        assert terms == []

    def test_with_graph_context(self):
        ctx = {"python": ["django", "fastapi", "flask"]}
        expanded, terms = query_expand("python", graph_context=ctx)
        assert "django" in expanded or "fastapi" in expanded
        assert len(terms) > 0

    def test_entity_boost(self):
        intent = QueryIntent(raw="python", entities=["Django"])
        ctx = {}
        expanded, terms = query_expand("python", intent=intent, graph_context=ctx)
        # Without graph context, no expansion
        assert expanded == "python"


class TestFormatContext:
    def test_empty(self):
        assert format_context([], query="test") == ""

    def test_single_result(self):
        results = [{"score": 0.9, "content": "test content"}]
        ctx = format_context(results, query="test")
        assert "test" in ctx
        assert "0.90" in ctx

    def test_with_confidence(self):
        results = [{"score": 0.9, "content": "test", "confidence": {"overall": 0.85}}]
        ctx = format_context(results, query="test", include_confidence=True)
        assert "0.85" in ctx

    def test_max_memories(self):
        results = [{"score": 0.5, "content": f"item {i}"} for i in range(20)]
        ctx = format_context(results, query="test", max_memories=5)
        assert ctx.count("\n- [") <= 5  # header line + 5 items = 6 total lines maximum


class TestComputeResultConfidence:
    def test_defaults(self):
        cs = compute_result_confidence({"score": 0.8, "quality_score": 7.0})
        assert 0 <= cs.overall <= 1


class TestRetrievalPipeline:
    def test_empty_results(self):
        def retrieve_fn(q, limit):
            return []

        pipeline = RetrievalPipeline()
        result = pipeline.run("test", retrieve_fn=retrieve_fn)
        assert isinstance(result, PipelineResult)
        assert result.query == "test"
        assert len(result.reranked) == 0

    def test_with_candidates(self):
        candidates = [
            {"neuron_id": "n1", "content": "python deployment with kubernetes"},
            {"neuron_id": "n2", "content": "gardening tips for roses"},
        ]

        def retrieve_fn(q, limit):
            return candidates

        pipeline = RetrievalPipeline()
        result = pipeline.run("deploy python kubernetes", retrieve_fn=retrieve_fn)
        assert result.query == "deploy python kubernetes"
        assert len(result.reranked) > 0
        # The python-kubernetes result should rank higher
        assert result.reranked[0].neuron_id == "n1"

    def test_disabled_steps(self):
        cfg = RetrievalConfig(
            enable_parse=False, enable_expand=False,
            enable_rerank=False, enable_confidence=False,
        )

        def retrieve_fn(q, limit):
            return [{"neuron_id": "n1", "content": "test"}]

        pipeline = RetrievalPipeline(cfg)
        result = pipeline.run("test", retrieve_fn=retrieve_fn)
        assert len(result.reranked) == 1

    def test_no_rerank_enough(self):
        cfg = RetrievalConfig(enable_rerank=False, enable_confidence=False, enable_format=False)

        def retrieve_fn(q, limit):
            return [{"neuron_id": "n1", "content": "a"}, {"neuron_id": "n2", "content": "b"}]

        pipeline = RetrievalPipeline(cfg)
        result = pipeline.run("test", retrieve_fn=retrieve_fn)
        assert len(result.reranked) == 2

    def test_str_depthlevel(self):
        assert int(DepthLevel.INSTANT) == 0
        assert int(DepthLevel.CONTEXT) == 1
        assert int(DepthLevel.HABIT) == 2
        assert int(DepthLevel.DEEP) == 3
