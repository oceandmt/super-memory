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
import urllib.request
from pathlib import Path
from typing import Any

from .config import load_config

logger = logging.getLogger("super-memory.vector")

_HAS_SQLITE_VEC = importlib.util.find_spec("sqlite_vec") is not None


def _normalize(vector: list[float]) -> list[float]:
    """L2-normalize a vector to unit length.

    sqlite-vec vec0 ranks by L2 (Euclidean) distance. For UNIT vectors,
    L2 distance is a monotonic function of cosine similarity
    (||a-b||^2 = 2 - 2*cos), so normalizing on both store and query paths
    makes nearest-neighbor ranking equivalent to cosine and removes the
    magnitude bias that unnormalized vectors introduce. Zero vectors are
    returned unchanged.
    """
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return list(vector)
    return [x / norm for x in vector]


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
            dim = int(getattr(self.config, "embedding_dimension", 768) or 768)
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS embeddings
                USING vec0(
                    memory_id TEXT PRIMARY KEY,
                    embedding FLOAT[{dim}]
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
            vec_json = json.dumps(_normalize(vector))
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

        Returns list of (memory_id, score) pairs, sorted by score descending.
        NOTE: sqlite-vec vec0 uses L2 (Euclidean) distance by default, not
        cosine. The returned score is 1/(1+distance), a monotonic transform of
        L2 distance into a [0,1) similarity-like value (higher = closer). It is
        NOT cosine similarity.
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
                "SELECT memory_id, distance FROM embeddings WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (json.dumps(_normalize(vector)), top_k),
            ).fetchall()
            conn.close()

            # sqlite-vec returns distance where lower is better. Convert to
            # similarity-like score so callers can sort descending.
            return [(str(memory_id), 1.0 / (1.0 + float(distance))) for memory_id, distance in rows]
        except Exception as exc:
            logger.warning("Vector search failed: %s", exc)
            return []

    def search_text(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Embed text and search sqlite-vec for nearest memories."""
        vector = embed_text(text, config=self.config)
        if vector is None:
            return []
        return self.search_similar(vector, top_k=top_k)

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
    """Compute cosine similarity between two vectors.

    Vectors of different dimensionality are not comparable; zero-padding the
    shorter one fabricates a score, so we refuse and return 0.0 instead.
    """
    if len(a) != len(b):
        logger.warning("cosine dim mismatch: %d vs %d -- refusing to compare", len(a), len(b))
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


_KEEP_ALIVE_MODEL: str | None = None


def warmup_embedding_model(config=None) -> bool:
    """Ensure the embedding model is loaded and kept warm.
    Sends a warm-up request with keep_alive=30m.
    Returns True if model is ready, False if unavailable.
    """
    global _KEEP_ALIVE_MODEL
    cfg = config or load_config()
    model = getattr(cfg, "embedding_model", "nomic-embed-text")
    if _KEEP_ALIVE_MODEL == model:
        return True  # Already warmed up
    # Use the same /api/embed endpoint with a tiny input to warm the model
    endpoint = getattr(cfg, "embedding_endpoint", "http://127.0.0.1:11434/api/embed")
    try:
        # Warm by sending a tiny embed request — this loads the model
        payload = json.dumps({"model": model, "input": ["warm"]}).encode("utf-8")
        req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            json.loads(resp.read())
        _KEEP_ALIVE_MODEL = model
        logger.info("Embedding model %s warmed up", model)
        return True
    except Exception as exc:
        logger.warning("Embedding model warmup failed: %s", exc)
        return False


def embed_text(text: str, config=None, timeout: int = 300) -> list[float] | None:
    """Embed text using the configured provider.

    Currently supports Ollama's /api/embed endpoint. Returns None when
    embeddings are disabled or unavailable.

    Automatically warms up the model on first call. Uses generous
    timeout (default 300s) for CPU-bound large texts.
    """
    cfg = config or load_config()
    provider = (getattr(cfg, "embedding_provider", "ollama") or "ollama").lower()
    if provider in {"disabled", "none"}:
        return None
    if provider != "ollama":
        logger.warning("Unsupported embedding provider: %s", provider)
        return None

    # Ensure model is warm
    warmup_embedding_model(config=cfg)

    endpoint = getattr(cfg, "embedding_endpoint", "http://127.0.0.1:11434/api/embed")
    model = getattr(cfg, "embedding_model", "nomic-embed-text")
    try:
        # Send the full text in a single request. The previous implementation
        # split on raw CHARACTER count (2000) and averaged per-chunk embeddings,
        # which corrupts semantics (mean of chunk vectors != vector of the text
        # and cuts mid-word/mid-token). nomic-embed-text handles long inputs, and
        # embed_text already uses a generous timeout, so let the model own it.
        # If a hard cap is ever needed it should be token-based on a word boundary,
        # not a naive character slice + average.
        input_text = text or ""
        payload = json.dumps({"model": model, "input": [input_text]}).encode("utf-8")
        req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        embeddings = data.get("embeddings") or []
        if not embeddings:
            return None
        return list(embeddings[0])
    except Exception as exc:
        logger.warning("Embedding request failed: %s", exc)
        return None


def rerank_by_embedding(
    candidates: list[dict[str, Any]],
    query_vector: list[float] | str,
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

    if isinstance(query_vector, str):
        vector = embed_text(query_vector, config=config)
        if vector is None:
            return candidates[:top_k]
    else:
        vector = query_vector

    semantic = store.search_similar(vector, top_k=max(top_k * 5, len(candidates)))
    score_by_id = {memory_id: score for memory_id, score in semantic}

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for idx, cand in enumerate(candidates):
        cand_id = str(cand.get("id", ""))
        # Preserve lexical order when candidate has no vector hit.
        scored.append((score_by_id.get(cand_id, -idx / 1_000_000), -idx, cand))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [cand for _, _, cand in scored[:top_k]]
