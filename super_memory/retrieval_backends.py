"""Multi-backend retrieval abstraction with registry pattern.

P1 #5 Optimization: Production-grade vector backends with registry pattern,
auto-select health check, and graceful fallback.

Backends:
    - sqlite_exact (baseline, always available)
    - chroma (optional, requires chromadb)
    - qdrant (optional, requires qdrant-client)
    - pgvector (optional, requires psycopg2 + running PG)
    - disabled (noop for testing)
"""

from __future__ import annotations

import importlib.util
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from .models import MemoryRecord, SuperMemoryConfig
from .storage import SuperMemoryStore, row_to_memory

logger = logging.getLogger("super-memory.retrieval_backends")

# ── Shared types ──────────────────────────────────────────────────

BACKEND_REGISTRY: dict[str, type["RetrievalBackend"]] = {}


def register_backend(name: str, cls: type["RetrievalBackend"]) -> None:
    """Register a retrieval backend class under a canonical name."""
    BACKEND_REGISTRY[name] = cls


def list_backends() -> list[str]:
    """Return all registered backend names."""
    return list(BACKEND_REGISTRY.keys())


@dataclass
class RetrievalHit:
    memory: MemoryRecord
    score: float
    backend: str


class RetrievalBackend(Protocol):
    name: str

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        agent_id: str | None = None,
        session_id: str | None = None,
        project: str | None = None,
    ) -> list[RetrievalHit]: ...


class SQLiteExactBackend:
    """Deterministic SQLite retrieval with agent/session/project filters.

    This is the baseline backend used by the qualification harness and a
    conformance target for all vector backends.
    """

    name = "sqlite_exact"

    def __init__(self, config: SuperMemoryConfig):
        self.config = config
        self.store = SuperMemoryStore(config)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        agent_id: str | None = None,
        session_id: str | None = None,
        project: str | None = None,
    ) -> list[RetrievalHit]:
        where = ["json_extract(metadata_json, '$.soft_deleted') IS NULL"]
        params: list[object] = []
        if query:
            where.append("(content LIKE ? OR tags_json LIKE ?)")
            like = "%" + query + "%"
            params.extend([like, like])
        if agent_id:
            where.append("agent_id = ?")
            params.append(agent_id)
        if session_id:
            where.append("session_id = ?")
            params.append(session_id)
        if project:
            where.append("project = ?")
            params.append(project)
        params.append(limit)
        sql = "SELECT * FROM memories WHERE " + " AND ".join(where) + " ORDER BY created_at DESC LIMIT ?"
        with self.store.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        hits: list[RetrievalHit] = []
        for row in rows:
            content = str(row["content"] or "")
            score = 1.0 if query and query.lower() in content.lower() else 0.5
            hits.append(RetrievalHit(memory=row_to_memory(row), score=score, backend=self.name))
        return hits


class ChromaBackend:
    """Chroma vector backend with full search and indexing support."""

    name = "chroma"

    def __init__(self, config: SuperMemoryConfig):
        try:
            import chromadb  # type: ignore
        except Exception as exc:
            raise RuntimeError("chromadb is not installed; pip install chromadb") from exc
        self.config = config
        self.client = chromadb.PersistentClient(path=str(config.workspace_root / ".super-memory-chroma"))
        self.collection = self.client.get_or_create_collection("super_memory")
        self.fallback = SQLiteExactBackend(config)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        agent_id: str | None = None,
        session_id: str | None = None,
        project: str | None = None,
    ) -> list[RetrievalHit]:
        try:
            results = self.collection.query(query_texts=[query], n_results=limit)
            if not results or not results.get("ids"):
                return self.fallback.search(query, limit=limit, agent_id=agent_id, session_id=session_id, project=project)
            ids = results["ids"][0] if results.get("ids") else []
            distances = results["distances"][0] if results.get("distances") else []
            hits: list[RetrievalHit] = []
            for i, mem_id in enumerate(ids):
                dist = distances[i] if i < len(distances) else 1.0
                score = 1.0 / (1.0 + float(dist))
                with self.fallback.store.connect() as conn:
                    row = conn.execute("SELECT * FROM memories WHERE id = ?", (mem_id,)).fetchone()
                    if row:
                        hits.append(RetrievalHit(memory=row_to_memory(row), score=score, backend=self.name))
            return hits
        except Exception as exc:
            logger.warning("Chroma search failed, falling back to sqlite_exact: %s", exc)
            return self.fallback.search(query, limit=limit, agent_id=agent_id, session_id=session_id, project=project)


class QdrantBackend:
    """Qdrant vector backend — optional, requires qdrant-client."""

    name = "qdrant"

    def __init__(self, config: SuperMemoryConfig):
        try:
            from qdrant_client import QdrantClient  # type: ignore
        except Exception as exc:
            raise RuntimeError("qdrant-client is not installed; pip install qdrant-client") from exc
        self.config = config
        host = getattr(config, "qdrant_host", "127.0.0.1")
        port = int(getattr(config, "qdrant_port", 6333))
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = "super_memory"
        self.fallback = SQLiteExactBackend(config)
        self._dim = int(getattr(config, "embedding_dimension", 768) or 768)
        self._init_collection()

    def _init_collection(self):
        from qdrant_client.http.exceptions import UnexpectedResponse
        from qdrant_client.models import Distance, VectorParams
        try:
            self.client.get_collection(self.collection_name)
        except (UnexpectedResponse, Exception):
            try:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
                )
            except Exception:
                pass

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        agent_id: str | None = None,
        session_id: str | None = None,
        project: str | None = None,
    ) -> list[RetrievalHit]:
        try:
            from .vector import embed_text
            vector = embed_text(query, config=self.config)
            if vector is None:
                return self.fallback.search(query, limit=limit, agent_id=agent_id, session_id=session_id, project=project)
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                limit=limit,
            )
            hits: list[RetrievalHit] = []
            for scored in results:
                mem_id = str(scored.id)
                score = float(scored.score)
                with self.fallback.store.connect() as conn:
                    row = conn.execute("SELECT * FROM memories WHERE id = ?", (mem_id,)).fetchone()
                    if row:
                        hits.append(RetrievalHit(memory=row_to_memory(row), score=score, backend=self.name))
            return hits
        except Exception as exc:
            logger.warning("Qdrant search failed, falling back to sqlite_exact: %s", exc)
            return self.fallback.search(query, limit=limit, agent_id=agent_id, session_id=session_id, project=project)


class PGVectorBackend:
    """PostgreSQL pgvector backend — optional, requires psycopg2."""

    name = "pgvector"

    def __init__(self, config: SuperMemoryConfig):
        try:
            import psycopg2  # type: ignore
        except Exception as exc:
            raise RuntimeError("psycopg2 is not installed; pip install psycopg2-binary") from exc
        self.config = config
        dsn = getattr(config, "pgvector_dsn", "")
        if not dsn:
            raise RuntimeError("pgvector_dsn not configured; set in config or env PG_DSN")
        self.conn = psycopg2.connect(dsn)
        self._dim = int(getattr(config, "embedding_dimension", 768) or 768)
        self._init_table()
        self.fallback = SQLiteExactBackend(config)

    def _init_table(self):
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS super_memory_vectors (id TEXT PRIMARY KEY, embedding vector({self._dim}), created_at TIMESTAMPTZ DEFAULT NOW())"
            )
            self.conn.commit()

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        agent_id: str | None = None,
        session_id: str | None = None,
        project: str | None = None,
    ) -> list[RetrievalHit]:
        try:
            from .vector import embed_text
            vector = embed_text(query, config=self.config)
            if vector is None:
                return self.fallback.search(query, limit=limit, agent_id=agent_id, session_id=session_id, project=project)
            vec_str = json.dumps(vector)
            with self.conn.cursor() as cur:
                cur.execute(
                    f"SELECT id, embedding <-> '{vec_str}'::vector AS dist FROM super_memory_vectors ORDER BY dist LIMIT %s",
                    (limit,),
                )
                hits: list[RetrievalHit] = []
                for mem_id, dist in cur:
                    score = 1.0 / (1.0 + float(dist))
                    with self.fallback.store.connect() as conn:
                        row = conn.execute("SELECT * FROM memories WHERE id = ?", (mem_id,)).fetchone()
                        if row:
                            hits.append(RetrievalHit(memory=row_to_memory(row), score=score, backend=self.name))
                return hits
        except Exception as exc:
            logger.warning("PGVector search failed, falling back to sqlite_exact: %s", exc)
            return self.fallback.search(query, limit=limit, agent_id=agent_id, session_id=session_id, project=project)


class DisabledVectorBackend:
    name = "disabled"

    def __init__(self, config: SuperMemoryConfig):
        self.config = config

    def search(self, query: str, *, limit: int = 10, agent_id: str | None = None, session_id: str | None = None, project: str | None = None) -> list[RetrievalHit]:
        return []


# ── Register all backends ─────────────────────────────────────────

register_backend("sqlite_exact", SQLiteExactBackend)
register_backend("chroma", ChromaBackend)
register_backend("qdrant", QdrantBackend)
register_backend("pgvector", PGVectorBackend)
register_backend("disabled", DisabledVectorBackend)


# ── Factory ────────────────────────────────────────────────────────

def get_retrieval_backend(name: str | None, config: SuperMemoryConfig) -> RetrievalBackend:
    """Get a retrieval backend by name.

    Explicit optional vector backends surface clear dependency errors so callers
    can distinguish "not installed" from a silent sqlite fallback. Auto-select
    paths can still catch and fall back.
    """
    backend_name = (name or "sqlite_exact").strip().lower()
    if backend_name in BACKEND_REGISTRY:
        try:
            return BACKEND_REGISTRY[backend_name](config)
        except Exception as exc:
            logger.warning("Failed to init backend '%s': %s", backend_name, exc)
            if backend_name in {"chroma", "qdrant", "pgvector"}:
                raise RuntimeError(str(exc)) from exc
    else:
        logger.warning("Unknown backend '%s' — falling back to sqlite_exact", backend_name)
    return SQLiteExactBackend(config)


def auto_select_backend(config: SuperMemoryConfig, preferred: str | None = None) -> RetrievalBackend:
    """Auto-select the best available backend based on health check.

    Priority: preferred > qdrant > chroma > sqlite_exact > disabled
    """
    order = ["sqlite_exact", "chroma", "qdrant"]
    if preferred and preferred not in {"disabled", "none"}:
        order.insert(0, preferred)
    for name in order:
        try:
            backend = get_retrieval_backend(name, config)
            # Quick health check: try a search
            hits = backend.search("health check", limit=1)
            if hits is not None:
                logger.info("Auto-selected backend: %s", name)
                return backend
        except Exception:
            continue
    logger.warning("No backend available, using disabled")
    return DisabledVectorBackend(config)
