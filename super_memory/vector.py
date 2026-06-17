"""Vector embedding store for Super-Memory.

Provides a VectorStore abstraction over sqlite-vec for embedding-based
semantic recall. sqlite-vec is an optional dependency — when not installed,
the store degrades gracefully with a logging stub.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import math
from pathlib import Path
from typing import Any

from .config import load_config

logger = logging.getLogger("super-memory.vector")

_HAS_SQLITE_VEC = importlib.util.find_spec("sqlite_vec") is not None


class VectorStore:
    """Vector embedding store backed by sqlite-vec.

    When sqlite-vec is not available, all operations are no-ops that
    log a warning.

    Usage:
        store = VectorStore(config)
        store.add_embedding("mem-001", [0.1, 0.2, ...])
        results = store.search_similar(query_vector, top_k=5)
        store.delete_embedding("mem-001")
    """

    def __init__(self, config=None):
        self.config = config or load_config()
        self._available = _HAS_SQLITE_VEC
        self.db_path = Path(self.config.workspace_root) / "data" / "vectors.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._available:
            logger.info("sqlite-vec not installed; vector search disabled")
        else:
            self._init_db()

    def _init_db(self) -> None:
        """Initialize the vector table in sqlite-vec."""
        if not self._available:
            return
        try:
            import sqlite3

            import sqlite_vec
            conn = sqlite3.connect(str(self.db_path))
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS embeddings
                USING vec0(
                    memory_id TEXT PRIMARY KEY,
                    embedding FLOAT[1536]
                )
                """
            )
            conn.close()
        except Exception as exc:
            logger.warning("Failed to initialize vector store: %s", exc)
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def add_embedding(self, memory_id: str, vector: list[float]) -> bool:
        """Add or update an embedding vector for a memory.

        Returns True on success, False if vector store is unavailable.
        """
        if not self._available:
            logger.debug("Vector store unavailable — skipping add_embedding for %s", memory_id)
            return False
        try:
            import sqlite3

            import sqlite_vec
            conn = sqlite3.connect(str(self.db_path))
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            # Serialize vector as JSON for storage
            vec_json = json.dumps(vector)
            conn.execute(
                """
                INSERT OR REPLACE INTO embeddings (memory_id, embedding)
                VALUES (?, ?)
                """,
                (memory_id, vec_json),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as exc:
            logger.warning("Failed to add embedding for %s: %s", memory_id, exc)
            return False

    def search_similar(
        self,
        vector: list[float],
        top_k: int = 5,
    ) -> list[tuple[str, float]]:
        """Search for memories with embeddings most similar to the query vector.

        Returns list of (memory_id, cosine_similarity) pairs, sorted by
        similarity descending.
        """
        if not self._available:
            logger.debug("Vector store unavailable — returning empty results")
            return []
        try:
            import sqlite3

            import sqlite_vec
            conn = sqlite3.connect(str(self.db_path))
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            rows = conn.execute(
                "SELECT memory_id, embedding FROM embeddings"
            ).fetchall()
            conn.close()

            # Compute cosine similarity in Python
            scored: list[tuple[str, float]] = []
            for memory_id, emb_json in rows:
                try:
                    emb = json.loads(emb_json)
                    sim = _cosine_similarity(vector, emb)
                    scored.append((memory_id, sim))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue

            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_k]
        except Exception as exc:
            logger.warning("Vector search failed: %s", exc)
            return []

    def delete_embedding(self, memory_id: str) -> bool:
        """Remove an embedding for a memory.

        Returns True on success, False if unavailable or not found.
        """
        if not self._available:
            logger.debug("Vector store unavailable — skipping delete_embedding for %s", memory_id)
            return False
        try:
            import sqlite3

            import sqlite_vec
            conn = sqlite3.connect(str(self.db_path))
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.execute(
                "DELETE FROM embeddings WHERE memory_id = ?",
                (memory_id,),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as exc:
            logger.warning("Failed to delete embedding for %s: %s", memory_id, exc)
            return False


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        # Pad the shorter vector with zeros
        max_len = max(len(a), len(b))
        a = a + [0.0] * (max_len - len(a))
        b = b + [0.0] * (max_len - len(b))
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def rerank_by_embedding(
    candidates: list[dict[str, Any]],
    query_vector: list[float],
    top_k: int = 10,
    config=None,
) -> list[dict[str, Any]]:
    """Rerank recall candidates by embedding similarity.

    This is the integration point wired into hybrid_recall.py.
    If vector store is unavailable, returns candidates unchanged.

    Args:
        candidates: List of recall result dicts. Each must have an 'id' key.
        query_vector: The embedding of the query text.
        top_k: Number of top results to return.
        config: SuperMemoryConfig instance.

    Returns:
        Reranked list of candidate dicts, truncated to top_k.
    """
    store = VectorStore(config=config)
    if not store.available:
        return candidates[:top_k]

    # Score each candidate by cosine similarity
    scored: list[tuple[float, dict[str, Any]]] = []
    for cand in candidates:
        cand_id = str(cand.get("id", ""))
        results = store.search_similar(query_vector, top_k=1)
        # Check if this candidate has a stored embedding
        sim = 0.0
        for eid, similarity in results:
            if eid == cand_id:
                sim = similarity
                break
        # Fallback: use zero-vector comparison (candidate text embedding
        # wasn't stored, so use the query vector similarity scoring from
        # the store's index). If no stored embedding, keep original rank.
        if sim == 0.0:
            scored.append((float(len(scored)), cand))
        else:
            scored.append((sim, cand))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [cand for _, cand in scored[:top_k]]
