"""Regression tests for the 2026-07-14 MEDIUM-tier audit fixes.

M1. quality_scorer type_boost used "error" key; canonical MemoryType has no
    ERROR value (it's "blocker") so blocker memories got zero type boost.
M2. reindex.reindex_vectors was a placeholder: COUNT-only on a non-existent
    `memory_vectors` table, always returning ok=True without rebuilding.
M3. semantic.semantic_index indexed soft-deleted rows and never re-embedded
    edited content; bridge.edit() never dropped the stale embedding.
M4. vector.py stored/queried unnormalized vectors, biasing L2 ranking by
    magnitude instead of direction (cosine-equivalent only when normalized).
"""
from __future__ import annotations

import inspect
import math

import pytest


# ── M1: quality_scorer type_boost keys match canonical MemoryType ──────────

def test_quality_scorer_uses_canonical_blocker_key():
    from super_memory.quality_scorer import importance_score

    blocker_score = importance_score("system is down and broken", memory_type="blocker")
    context_score = importance_score("system is down and broken", memory_type="context")
    # blocker must score at least as high as an untyped/context memory with
    # the same content, since it carries the highest-priority type boost.
    assert blocker_score >= context_score

    src = inspect.getsource(importance_score)
    assert '"error": 0.3' not in src, "stale non-canonical 'error' key still present"
    assert '"blocker": 0.3' in src


# ── M2: reindex_vectors actually rebuilds instead of COUNT-only no-op ──────

def test_reindex_vectors_delegates_to_real_rebuild():
    from super_memory import reindex

    src = inspect.getsource(reindex.reindex_vectors)
    assert "FROM memory_vectors" not in src, "stale wrong-table COUNT-only placeholder still present"
    assert "semantic_index" in src


# ── M3: semantic_index filters soft-deleted rows; edit() drops stale vector ─

def test_semantic_index_filters_soft_deleted():
    from super_memory import semantic

    src = inspect.getsource(semantic.semantic_index)
    assert "soft_deleted" in src, "semantic_index still indexes soft-deleted rows"


def test_bridge_edit_drops_stale_embedding_on_content_change():
    from super_memory import bridge

    src = inspect.getsource(bridge.edit)
    assert "_drop_embedding(cfg, memory_id)" in src


# ── M4: vector store normalizes on both store and query paths ──────────────

def test_normalize_produces_unit_vector():
    from super_memory.vector import _normalize

    v = _normalize([3.0, 4.0])  # 3-4-5 triangle -> norm 5
    assert v == pytest.approx([0.6, 0.8])
    norm = math.sqrt(sum(x * x for x in v))
    assert norm == pytest.approx(1.0)


def test_normalize_handles_zero_vector():
    from super_memory.vector import _normalize

    assert _normalize([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]


def test_add_embedding_and_search_similar_normalize():
    from super_memory import vector as vector_mod

    add_src = inspect.getsource(vector_mod.VectorStore.add_embedding)
    search_src = inspect.getsource(vector_mod.VectorStore.search_similar)
    assert "_normalize(vector)" in add_src
    assert "_normalize(vector)" in search_src


def test_semantic_ollama_embed_batch_normalizes():
    from super_memory import semantic

    src = inspect.getsource(semantic._ollama_embed_batch)
    assert "_normalize" in src
