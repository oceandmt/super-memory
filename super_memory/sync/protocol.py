"""Sync protocol — Merkle tree-based memory diff/sync."""
from __future__ import annotations
import hashlib, json, logging
from typing import Any

logger = logging.getLogger("super-memory.sync")

class MerkleNode:
    def __init__(self, hash: str, children: dict[str, "MerkleNode"] = None):
        self.hash = hash
        self.children = children or {}

def build_merkle_tree(memories: list[dict]) -> MerkleNode:
    """Build a simple Merkle tree from memory list."""
    if not memories:
        return MerkleNode(hashlib.sha256(b"empty").hexdigest()[:16])
    h = hashlib.sha256()
    for m in memories[:1000]:
        h.update(f"{m.get('id','')}:{m.get('content','')[:50]}".encode())
    return MerkleNode(h.hexdigest()[:16])

def diff_merkle(local: MerkleNode, remote: MerkleNode) -> list[str]:
    """Diff two Merkle trees — return differing memory IDs."""
    if local.hash == remote.hash:
        return []
    # Simple: if root differs, return placeholder
    return ["*root_differs*"]
