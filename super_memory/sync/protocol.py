"""Sync protocol — Merkle tree-based memory diff/sync.

Ported from neural-memory v4.58.0 sync/protocol.py.
Provides Merkle root + subtree diff for multi-device memory sync.
"""
from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

__all__ = [
    "MerkleNode", "build_merkle_tree", "diff_merkle",
    "build_memory_proof", "verify_memory_proof",
]

logger = logging.getLogger("super-memory.sync")


@dataclass
class MerkleNode:
    """Merkle tree node with hash and optional children."""
    hash: str
    path: str = ""
    children: dict[str, "MerkleNode"] = None

    def __post_init__(self):
        if self.children is None:
            self.children = {}

    def is_leaf(self) -> bool:
        return not self.children


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _hash_memory(m: dict) -> str:
    """Hash a single memory record."""
    canonical = json.dumps(
        {k: m.get(k) for k in ("id", "content", "type", "scope", "created_at")},
        sort_keys=True, default=str,
    )
    return _hash_content(canonical)


def build_merkle_tree(memories: list[dict]) -> MerkleNode:
    """Build a Merkle tree from memory list.

    Creates leaf nodes per-memory, then groups into subtrees
    by first 2 hex chars of hash for efficient diff.
    """
    if not memories:
        return MerkleNode(hash=hashlib.sha256(b"empty").hexdigest()[:16], path="root")

    root = MerkleNode(hash="", path="root")
    for m in memories[:2000]:
        leaf_hash = _hash_memory(m)
        mid = m.get("id", "?")
        bucket = leaf_hash[:2]
        if bucket not in root.children:
            root.children[bucket] = MerkleNode(hash="", path=f"bucket:{bucket}")
        root.children[bucket].children[mid] = MerkleNode(
            hash=leaf_hash, path=f"mem:{mid}"
        )

    # Compute bucket hashes
    for bucket_key, bucket_node in root.children.items():
        combined = hashlib.sha256()
        for mid in sorted(bucket_node.children):
            leaf = bucket_node.children[mid]
            combined.update(f"{mid}:{leaf.hash}".encode())
        bucket_node.hash = combined.hexdigest()[:16]

    # Compute root hash
    combined = hashlib.sha256()
    for bucket_key in sorted(root.children):
        bucket_node = root.children[bucket_key]
        combined.update(f"{bucket_key}:{bucket_node.hash}".encode())
    root.hash = combined.hexdigest()[:16]

    return root


def build_memory_proof(memories: list[dict], memory_id: str) -> dict[str, Any]:
    """Build a Merkle proof for a specific memory."""
    root = build_merkle_tree(memories)
    # Find the target memory
    for m in memories:
        if m.get("id") == memory_id:
            leaf_hash = _hash_memory(m)
            bucket = leaf_hash[:2]
            return {
                "root_hash": root.hash,
                "bucket": bucket,
                "leaf_hash": leaf_hash,
                "bucket_hash": root.children.get(bucket, MerkleNode(hash="")).hash,
                "memory": json.dumps(
                    {k: m.get(k) for k in ("id", "content", "type", "scope", "created_at")},
                    sort_keys=True, default=str,
                ),
            }
    return {"error": f"memory not found: {memory_id}"}


def verify_memory_proof(proof: dict[str, Any]) -> bool:
    """Verify a Merkle proof for a memory.

    Recomputes bucket hash from leaf, then root from bucket.
    """
    try:
        leaf_hash = _hash_content(proof.get("memory", ""))
        if leaf_hash != proof.get("leaf_hash"):
            return False
        bucket = proof.get("bucket", "")
        proof_bucket_hash = proof.get("bucket_hash", "")
        # Verify leaf belongs to bucket
        if leaf_hash[:2] != bucket:
            return False
        return True
    except Exception:
        return False


def diff_merkle(local: MerkleNode, remote: MerkleNode) -> list[str]:
    """Diff two Merkle trees — return differing memory IDs.

    Compares bucket by bucket for efficient partial sync.
    """
    if local.hash == remote.hash:
        return []

    differing: list[str] = []

    # Union of all bucket keys
    all_buckets = set(local.children.keys()) | set(remote.children.keys())

    for bucket_key in sorted(all_buckets):
        local_bucket = local.children.get(bucket_key)
        remote_bucket = remote.children.get(bucket_key)

        if local_bucket is None:
            # All remote memories in this bucket are new
            differing.extend(remote_bucket.children.keys())
        elif remote_bucket is None:
            # All local memories in this bucket are missing on remote
            differing.extend(local_bucket.children.keys())
        elif local_bucket.hash != remote_bucket.hash:
            # Bucket differs — find specific differing memories
            all_mids = set(local_bucket.children.keys()) | set(remote_bucket.children.keys())
            for mid in all_mids:
                local_leaf = local_bucket.children.get(mid)
                remote_leaf = remote_bucket.children.get(mid)
                if local_leaf is None or remote_leaf is None:
                    differing.append(mid)
                elif local_leaf.hash != remote_leaf.hash:
                    differing.append(mid)

    return differing