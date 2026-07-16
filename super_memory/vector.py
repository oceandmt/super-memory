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
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical_contract import (
    CANONICAL_CONTRACT_VERSION,
    DEFAULT_CANONICAL_LAYER,
    canonical_revision,
)
from .config import load_config

logger = logging.getLogger("super-memory.vector")

_HAS_SQLITE_VEC = importlib.util.find_spec("sqlite_vec") is not None

# Authority contract: sqlite-vec payloads and their verification metadata live
# in data/vectors.sqlite3.  The main database's memory_vectors table is retained
# as a legacy write-contract/health cache; it is never read as semantic-recall
# authority and is never destructively migrated by this module.
VECTOR_AUTHORITY = "data/vectors.sqlite3"
LEGACY_VECTOR_COMPATIBILITY = "main_db.memory_vectors:non_authoritative_cache"
_VECTOR_METADATA_TABLE = "embedding_metadata"
_DEFAULT_AUDIT_LIMIT = 200
_MAX_AUDIT_LIMIT = 5_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_limit(limit: int) -> int:
    return min(max(int(limit), 1), _MAX_AUDIT_LIMIT)


def _embedding_identity(config: Any) -> tuple[str, str, int]:
    return (
        str(getattr(config, "embedding_provider", "ollama") or "ollama").lower(),
        str(getattr(config, "embedding_model", "nomic-embed-text") or "nomic-embed-text"),
        int(getattr(config, "embedding_dimension", 768) or 768),
    )


def _canonical_db_path(config: Any) -> Path:
    return Path(config.workspace_root) / str(config.sqlite_path)


def _canonical_for_memory(
    config: Any,
    memory_id: str,
    layer: str = DEFAULT_CANONICAL_LAYER,
):
    """Read and hash actual canonical content; cached content_hash is ignored."""
    db_path = _canonical_db_path(config)
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                """SELECT id,layer,content FROM memories
                   WHERE id=? AND layer=?
                     AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1
                   LIMIT 1""",
                (str(memory_id), str(layer)),
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return canonical_revision(str(row[0]), str(row[2] or ""), str(row[1]))


def _ensure_vector_metadata(conn: sqlite3.Connection) -> None:
    """Create the additive verification sidecar for sqlite-vec payloads."""
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {_VECTOR_METADATA_TABLE} (
            memory_id TEXT PRIMARY KEY,
            canonical_id TEXT NOT NULL,
            canonical_layer TEXT NOT NULL DEFAULT 'workspace_markdown',
            source_hash TEXT NOT NULL,
            source_revision TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            contract_version TEXT NOT NULL DEFAULT '1',
            status TEXT NOT NULL DEFAULT 'active',
            status_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_verified_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_embedding_metadata_status
            ON {_VECTOR_METADATA_TABLE}(status);
        CREATE INDEX IF NOT EXISTS idx_embedding_metadata_revision
            ON {_VECTOR_METADATA_TABLE}(canonical_id,source_revision);
        """
    )


def _metadata_classification(
    metadata: dict[str, Any] | None,
    canonical: Any,
    provider: str,
    model: str,
    dimensions: int,
    *,
    has_embedding: bool = True,
) -> tuple[str, str | None]:
    """Return the deterministic desired status for one vector slot."""
    if not has_embedding:
        return "orphaned", "embedding_missing"
    if metadata is None:
        return "stale", "unverified_legacy_vector"
    if canonical is None:
        return "orphaned", "canonical_missing_or_deleted"
    checks = (
        (metadata.get("canonical_id") == canonical.canonical_id, "canonical_id_mismatch"),
        (metadata.get("canonical_layer") == canonical.layer, "canonical_layer_mismatch"),
        (metadata.get("source_hash") == canonical.source_hash, "source_hash_mismatch"),
        (metadata.get("source_revision") == canonical.source_revision, "source_revision_mismatch"),
        (metadata.get("provider") == provider, "provider_mismatch"),
        (metadata.get("model") == model, "model_mismatch"),
        (int(metadata.get("dimensions") or 0) == dimensions, "dimension_mismatch"),
        (
            metadata.get("contract_version") == CANONICAL_CONTRACT_VERSION,
            "contract_version_mismatch",
        ),
    )
    for valid, reason in checks:
        if not valid:
            return "stale", reason
    return "active", None


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
        """Initialize vector payload and revision-verification metadata."""
        if not self._available:
            return
        try:
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
            _ensure_vector_metadata(conn)
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("Failed to initialize vector store: %s", exc)
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def add_embedding(
        self,
        memory_id: str,
        vector: list[float],
        *,
        canonical_layer: str = DEFAULT_CANONICAL_LAYER,
    ) -> bool:
        """Add/update a vector only for the current canonical revision.

        The method intentionally fails closed when no live canonical row exists
        or dimensions do not match configured embedding identity.  Payload and
        metadata are committed atomically in the authoritative vector database.
        """
        if not self._available:
            logger.debug("Vector store unavailable — skipping add_embedding for %s", memory_id)
            return False
        provider, model, dimensions = _embedding_identity(self.config)
        canonical = _canonical_for_memory(self.config, memory_id, canonical_layer)
        if canonical is None:
            logger.warning("Refusing embedding for missing/deleted canonical memory %s", memory_id)
            return False
        if len(vector) != dimensions:
            logger.warning(
                "Refusing embedding for %s: dimension %d != configured %d",
                memory_id,
                len(vector),
                dimensions,
            )
            return False
        try:
            import sqlite_vec
            conn = sqlite3.connect(str(self.db_path))
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            _ensure_vector_metadata(conn)
            vec_json = json.dumps(_normalize(vector))
            # vec0 does not implement SQLite's INSERT OR REPLACE conflict
            # behavior reliably for an existing TEXT primary key.  Delete and
            # insert in the same transaction so a verified refresh replaces the
            # payload without leaving metadata ahead of the vector.
            conn.execute("DELETE FROM embeddings WHERE memory_id = ?", (memory_id,))
            conn.execute(
                "INSERT INTO embeddings (memory_id, embedding) VALUES (?, ?)",
                (memory_id, vec_json),
            )
            now = _now()
            conn.execute(
                f"""INSERT INTO {_VECTOR_METADATA_TABLE}
                    (memory_id,canonical_id,canonical_layer,source_hash,source_revision,
                     provider,model,dimensions,contract_version,status,status_reason,
                     created_at,updated_at,last_verified_at)
                    VALUES (?,?,?,?,?,?,?,?,?,'active',NULL,?,?,?)
                    ON CONFLICT(memory_id) DO UPDATE SET
                      canonical_id=excluded.canonical_id,
                      canonical_layer=excluded.canonical_layer,
                      source_hash=excluded.source_hash,
                      source_revision=excluded.source_revision,
                      provider=excluded.provider,
                      model=excluded.model,
                      dimensions=excluded.dimensions,
                      contract_version=excluded.contract_version,
                      status='active',status_reason=NULL,
                      updated_at=excluded.updated_at,
                      last_verified_at=excluded.last_verified_at""",
                (
                    str(memory_id),
                    canonical.canonical_id,
                    canonical.layer,
                    canonical.source_hash,
                    canonical.source_revision,
                    provider,
                    model,
                    dimensions,
                    CANONICAL_CONTRACT_VERSION,
                    now,
                    now,
                    now,
                ),
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
        Only candidates whose metadata matches live canonical content and the
        configured provider/model/dimension are returned. Legacy payloads with
        no metadata are deliberately quarantined until re-embedded.

        NOTE: sqlite-vec vec0 uses L2 (Euclidean) distance by default, not
        cosine. The returned score is 1/(1+distance), a monotonic transform of
        L2 distance into a [0,1) similarity-like value (higher = closer). It is
        NOT cosine similarity.
        """
        if not self._available:
            logger.debug("Vector store unavailable — returning empty results")
            return []
        provider, model, dimensions = _embedding_identity(self.config)
        if len(vector) != dimensions:
            logger.warning(
                "Refusing vector query: dimension %d != configured %d",
                len(vector),
                dimensions,
            )
            return []
        try:
            import sqlite_vec
            conn = sqlite3.connect(str(self.db_path))
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.row_factory = sqlite3.Row
            _ensure_vector_metadata(conn)
            rows = conn.execute(
                "SELECT memory_id, distance FROM embeddings WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (json.dumps(_normalize(vector)), top_k),
            ).fetchall()

            accepted: list[tuple[str, float]] = []
            for row in rows:
                memory_id = str(row["memory_id"])
                raw_meta = conn.execute(
                    f"SELECT * FROM {_VECTOR_METADATA_TABLE} WHERE memory_id=?",
                    (memory_id,),
                ).fetchone()
                metadata = dict(raw_meta) if raw_meta is not None else None
                layer = (
                    str(metadata.get("canonical_layer"))
                    if metadata and metadata.get("canonical_layer")
                    else DEFAULT_CANONICAL_LAYER
                )
                canonical = _canonical_for_memory(self.config, memory_id, layer)
                status, _reason = _metadata_classification(
                    metadata, canonical, provider, model, dimensions
                )
                if status == "active" and metadata and metadata.get("status") == "active":
                    accepted.append(
                        (memory_id, 1.0 / (1.0 + float(row["distance"])))
                    )
            conn.close()

            # sqlite-vec returns distance where lower is better. Convert to
            # similarity-like score so callers can sort descending.
            return accepted[:top_k]
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
            import sqlite_vec
            conn = sqlite3.connect(str(self.db_path))
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            # Ensure schema before beginning the payload/metadata mutation:
            # sqlite3.executescript() may commit a pending transaction.
            _ensure_vector_metadata(conn)
            conn.execute(
                "DELETE FROM embeddings WHERE memory_id = ?",
                (memory_id,),
            )
            conn.execute(
                f"DELETE FROM {_VECTOR_METADATA_TABLE} WHERE memory_id = ?",
                (memory_id,),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as exc:
            logger.warning("Failed to delete embedding for %s: %s", memory_id, exc)
            return False


def audit_vector_authority(config=None, limit: int = _DEFAULT_AUDIT_LIMIT) -> dict[str, Any]:
    """Audit authoritative vector payloads and metadata without mutation.

    ``data/vectors.sqlite3`` is the semantic-recall authority. The main SQLite
    database's ``memory_vectors`` table is reported as a compatibility cache;
    it is never imported, deleted, or accepted as recall authority here.
    """
    cfg = config or load_config()
    limit = _bounded_limit(limit)
    db_path = Path(cfg.workspace_root) / "data" / "vectors.sqlite3"
    provider, model, dimensions = _embedding_identity(cfg)
    result: dict[str, Any] = {
        "ok": True,
        "dry_run": True,
        "authority": VECTOR_AUTHORITY,
        "compatibility": LEGACY_VECTOR_COMPATIBILITY,
        "vector_db": str(db_path),
        "limit": limit,
        "scanned": 0,
        "active": [],
        "stale": [],
        "orphaned": [],
        "legacy_unverified": [],
        "legacy_memory_vectors": {"present": False, "rows": 0, "authoritative": False},
    }
    if not db_path.exists():
        result["counts"] = {"active": 0, "stale": 0, "orphaned": 0, "legacy_unverified": 0}
        return result

    try:
        import sqlite_vec

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        has_embeddings = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='embeddings'"
        ).fetchone()
        has_metadata = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (_VECTOR_METADATA_TABLE,),
        ).fetchone()
        ids = [] if not has_embeddings else [
            str(row[0])
            for row in conn.execute(
                "SELECT memory_id FROM embeddings ORDER BY memory_id LIMIT ?", (limit,)
            ).fetchall()
        ]
        for memory_id in ids:
            raw = (
                conn.execute(
                    f"SELECT * FROM {_VECTOR_METADATA_TABLE} WHERE memory_id=?", (memory_id,)
                ).fetchone()
                if has_metadata
                else None
            )
            metadata = dict(raw) if raw is not None else None
            layer = (
                str(metadata.get("canonical_layer"))
                if metadata and metadata.get("canonical_layer")
                else DEFAULT_CANONICAL_LAYER
            )
            canonical = _canonical_for_memory(cfg, memory_id, layer)
            status, reason = _metadata_classification(
                metadata, canonical, provider, model, dimensions
            )
            item = {
                "memory_id": memory_id,
                "status": status,
                "reason": reason,
                "metadata_status": metadata.get("status") if metadata else None,
            }
            if reason == "unverified_legacy_vector":
                result["legacy_unverified"].append(item)
            elif status == "orphaned":
                result["orphaned"].append(item)
            elif status == "stale" or not metadata or metadata.get("status") != "active":
                result["stale"].append(item)
            else:
                result["active"].append(item)
        result["scanned"] = len(ids)
        conn.close()
    except Exception as exc:
        result.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    canonical_db = Path(cfg.workspace_root) / cfg.sqlite_path
    if canonical_db.exists():
        with sqlite3.connect(str(canonical_db)) as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_vectors'"
            ).fetchone()
            if table:
                result["legacy_memory_vectors"] = {
                    "present": True,
                    "rows": int(conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0]),
                    "authoritative": False,
                }
    result["counts"] = {
        key: len(result[key])
        for key in ("active", "stale", "orphaned", "legacy_unverified")
    }
    return result


def reconcile_vector_authority(
    config=None,
    *,
    dry_run: bool = True,
    limit: int = _DEFAULT_AUDIT_LIMIT,
) -> dict[str, Any]:
    """Mark invalid vector metadata stale/orphaned; never delete payloads.

    Apply mode remains conservative: metadata-less legacy vectors are left
    metadata-less (and therefore query-ineligible) because no migration can
    prove which content/model produced them. Re-embedding is the only promotion
    path to ``active``. Repeated apply calls are idempotent.
    """
    cfg = config or load_config()
    audit = audit_vector_authority(cfg, limit=limit)
    if dry_run or not audit.get("ok"):
        return {"ok": bool(audit.get("ok")), "dry_run": True, "changed": 0, "audit": audit}
    db_path = Path(cfg.workspace_root) / "data" / "vectors.sqlite3"
    if not db_path.exists():
        return {"ok": True, "dry_run": False, "changed": 0, "audit": audit}
    changed = 0
    now = _now()
    with sqlite3.connect(str(db_path)) as conn:
        _ensure_vector_metadata(conn)
        for key in ("stale", "orphaned"):
            desired = "orphaned" if key == "orphaned" else "stale"
            for item in audit[key]:
                cursor = conn.execute(
                    f"""UPDATE {_VECTOR_METADATA_TABLE}
                        SET status=?,status_reason=?,updated_at=?,last_verified_at=?
                        WHERE memory_id=?
                          AND (status!=? OR COALESCE(status_reason,'')!=COALESCE(?,''))""",
                    (
                        desired,
                        item["reason"],
                        now,
                        now,
                        item["memory_id"],
                        desired,
                        item["reason"],
                    ),
                )
                changed += max(cursor.rowcount, 0)
        conn.commit()
    return {"ok": True, "dry_run": False, "changed": changed, "audit": audit}


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
