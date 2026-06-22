"""Tests for sync.protocol module — Merkle tree sync."""
from __future__ import annotations

from super_memory.sync.protocol import (
    MerkleNode,
    build_merkle_tree,
    diff_merkle,
    build_memory_proof,
    verify_memory_proof,
)


def _make_mem(id_: str, content: str = "test") -> dict:
    return {"id": id_, "content": content, "type": "context", "scope": "session", "created_at": "2026-01-01T00:00:00Z"}


def test_merkle_empty():
    node = build_merkle_tree([])
    assert node.hash is not None
    assert len(node.hash) == 16
    assert node.path == "root"


def test_merkle_nonempty():
    node = build_merkle_tree([_make_mem("1")])
    assert node.hash is not None
    assert len(node.hash) == 16
    assert "1" in [c for b in node.children.values() for c in b.children]


def test_merkle_multiple():
    mems = [_make_mem(str(i), f"content-{i}") for i in range(5)]
    node = build_merkle_tree(mems)
    assert node.hash is not None
    assert len(node.children) <= 16  # bucket count by hash prefix


def test_diff_identical():
    mems = [_make_mem("1"), _make_mem("2")]
    a = build_merkle_tree(mems)
    b = build_merkle_tree(mems)
    assert diff_merkle(a, b) == []


def _build_small_tree(memories: list[dict]) -> MerkleNode:
    """Build a simple flat Merkle tree for testing."""
    import hashlib

    root = MerkleNode(hash="", path="root")
    for m in memories:
        mid = m.get("id", "?")
        h = hashlib.sha256(m.get("content", "").encode()).hexdigest()[:16]
        bucket = h[:2]
        if bucket not in root.children:
            root.children[bucket] = MerkleNode(hash="", path=f"b:{bucket}")
        root.children[bucket].children[mid] = MerkleNode(hash=h, path=f"m:{mid}")

    # Compute bucket hashes
    for bk, bn in root.children.items():
        combined = hashlib.sha256()
        for mid in sorted(bn.children):
            combined.update(f"{mid}:{bn.children[mid].hash}".encode())
        bn.hash = combined.hexdigest()[:16]

    combined = hashlib.sha256()
    for bk in sorted(root.children):
        combined.update(f"{bk}:{root.children[bk].hash}".encode())
    root.hash = combined.hexdigest()[:16]
    return root


def test_diff_different():
    a_mems = [_make_mem("1", "hello")]
    b_mems = [_make_mem("1", "world")]
    a = _build_small_tree(a_mems)
    b = _build_small_tree(b_mems)
    diffs = diff_merkle(a, b)
    assert len(diffs) >= 1


def test_diff_missing_on_remote():
    a_mems = [_make_mem("1"), _make_mem("2")]
    b_mems = [_make_mem("1")]
    a = _build_small_tree(a_mems)
    b = _build_small_tree(b_mems)
    diffs = diff_merkle(a, b)
    assert "2" in diffs


def test_build_memory_proof():
    mems = [_make_mem("1", "proof test"), _make_mem("2", "other")]
    proof = build_memory_proof(mems, "1")
    assert proof.get("root_hash") is not None
    assert proof.get("leaf_hash") is not None
    assert proof.get("bucket") is not None
    assert proof.get("memory") is not None


def test_build_memory_proof_not_found():
    mems = [_make_mem("1", "test")]
    proof = build_memory_proof(mems, "nonexistent")
    assert "error" in proof


def test_verify_memory_proof_valid():
    mems = [_make_mem("1", "verify me")]
    proof = build_memory_proof(mems, "1")
    assert verify_memory_proof(proof) is True


def test_verify_memory_proof_tampered():
    mems = [_make_mem("1", "original")]
    proof = build_memory_proof(mems, "1")
    proof["memory"] = proof["memory"].replace("original", "tampered")
    assert verify_memory_proof(proof) is False


def test_verify_memory_proof_bad_data():
    assert verify_memory_proof({}) is False
    assert verify_memory_proof({"garbage": "data"}) is False


def test_merkle_node_is_leaf():
    leaf = MerkleNode(hash="abc", path="leaf")
    assert leaf.is_leaf() is True
    parent = MerkleNode(hash="def", path="parent", children={"child": leaf})
    assert parent.is_leaf() is False
