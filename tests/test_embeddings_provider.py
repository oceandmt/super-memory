"""Tests for embeddings.provider module."""
from __future__ import annotations
from super_memory.embeddings.provider import EmbeddingProvider

def test_init():
    ep = EmbeddingProvider("ollama", "nomic-embed-text")
    assert ep.name == "ollama"

def test_similarity_self():
    ep = EmbeddingProvider()
    v = [0.5, 0.5, 0.0]
    assert abs(ep.similarity(v, v) - 1.0) < 1e-6

def test_similarity_orthogonal():
    ep = EmbeddingProvider()
    assert ep.similarity([1, 0], [0, 1]) == 0.0
