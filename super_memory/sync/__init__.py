from __future__ import annotations
"""Sync subsystem — multi-device memory synchronization.
Ported from neural-memory v4.58.0 sync/.
"""

__all__ = ["MerkleNode", "build_merkle_tree", "diff_merkle", "build_memory_proof", "verify_memory_proof"]

from .protocol import MerkleNode, build_merkle_tree, diff_merkle, build_memory_proof, verify_memory_proof