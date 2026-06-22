"""Tests for sync.protocol module."""
from __future__ import annotations
from super_memory.sync.protocol import MerkleNode, build_merkle_tree

def test_merkle_empty():
    node = build_merkle_tree([])
    assert node.hash is not None

def test_merkle_nonempty():
    node = build_merkle_tree([{"id": "1", "content": "test"}])
    assert node.hash is not None
    assert len(node.hash) == 16
