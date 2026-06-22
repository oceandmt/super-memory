"""Tests for embeddings/provider module."""
from __future__ import annotations
from super_memory.embeddings.provider import EmbeddingProvider, get_embedding_provider

def test_default_provider():
    ep = EmbeddingProvider()
    assert ep.name == "ollama"
    assert ep.model == "nomic-embed-text"

def test_similarity_identical():
    ep = EmbeddingProvider()
    v = [1.0, 0.0, 0.0]
    assert abs(ep.similarity(v, v) - 1.0) < 1e-6

def test_similarity_orthogonal():
    ep = EmbeddingProvider()
    assert ep.similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

def test_get_provider_cache():
    p1 = get_embedding_provider("ollama")
    p2 = get_embedding_provider("ollama")
    assert p1 is p2
