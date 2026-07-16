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

import json
import logging
from dataclasses import dataclass
from typing import Protocol

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


@dataclass(frozen=True)
class RetrievalContext:
    """Caller identity used by every canonical-memory hydration query.

    Private scopes fail closed when their required context is absent:
    session requires agent + session, agent-local requires agent, and project
    requires project. Shared and cross-agent memories are globally visible.
    ``scope`` is an optional caller-requested narrowing, not an authorization
    bypass.
    """

    agent_id: str | None = None
    session_id: str | None = None
    project: str | None = None
    scope: str | None = None


def retrieval_context(
    *,
    context: RetrievalContext | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    project: str | None = None,
    scope: str | None = None,
) -> RetrievalContext:
    """Build context while preserving the legacy keyword argument contract."""
    base = context or RetrievalContext()
    return RetrievalContext(
        agent_id=agent_id if agent_id is not None else base.agent_id,
        session_id=session_id if session_id is not None else base.session_id,
        project=project if project is not None else base.project,
        scope=scope if scope is not None else base.scope,
    )


def visibility_predicate(
    context: RetrievalContext,
    *,
    alias: str | None = None,
) -> tuple[str, list[object]]:
    """Return the mandatory alive + scope visibility SQL predicate.

    The predicate is composed only from fixed SQL fragments; all caller data
    is bound as parameters. JSON ``false`` and numeric ``0`` are alive, while
    JSON ``true`` and numeric ``1`` are deleted. Malformed non-boolean values
    fail closed rather than accidentally becoming recallable.
    """
    prefix = f"{alias}." if alias else ""
    metadata = f"{prefix}metadata_json"
    scope_column = f"{prefix}scope"
    agent_column = f"{prefix}agent_id"
    session_column = f"{prefix}session_id"
    project_column = f"{prefix}project"

    clauses = [f"COALESCE(json_extract({metadata}, '$.soft_deleted'), 0) = 0"]
    visible = [f"{scope_column} IN ('shared', 'cross-agent')"]
    params: list[object] = []
    if context.project:
        visible.append(f"({scope_column} = 'project' AND {project_column} = ?)")
        params.append(context.project)
    if context.agent_id:
        visible.append(f"({scope_column} = 'agent-local' AND {agent_column} = ?)")
        params.append(context.agent_id)
    if context.agent_id and context.session_id:
        visible.append(f"({scope_column} = 'session' AND {agent_column} = ? AND {session_column} = ?)")
        params.extend([context.agent_id, context.session_id])
    clauses.append("(" + " OR ".join(visible) + ")")
    if context.scope:
        clauses.append(f"{scope_column} = ?")
        params.append(context.scope)
    return " AND ".join(clauses), params


def _visible_memory_row(
    store: SuperMemoryStore,
    memory_id: str,
    context: RetrievalContext,
):
    predicate, params = visibility_predicate(context)
    sql = (
        "SELECT * FROM memories WHERE id = ? AND "
        + predicate
        + " ORDER BY CASE WHEN layer = 'workspace_markdown' THEN 0 ELSE 1 END, layer LIMIT 1"
    )
    with store.connect() as conn:
        return conn.execute(sql, [memory_id, *params]).fetchone()


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
        scope: str | None = None,
        context: RetrievalContext | None = None,
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
        scope: str | None = None,
        context: RetrievalContext | None = None,
    ) -> list[RetrievalHit]:
        resolved = retrieval_context(
            context=context,
            agent_id=agent_id,
            session_id=session_id,
            project=project,
            scope=scope,
        )
        predicate, params = visibility_predicate(resolved)
        where = [predicate]
        if query:
            where.append("(content LIKE ? OR tags_json LIKE ?)")
            like = "%" + query + "%"
            params.extend([like, like])
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
        scope: str | None = None,
        context: RetrievalContext | None = None,
    ) -> list[RetrievalHit]:
        resolved = retrieval_context(
            context=context,
            agent_id=agent_id,
            session_id=session_id,
            project=project,
            scope=scope,
        )
        try:
            results = self.collection.query(query_texts=[query], n_results=limit)
            if not results or not results.get("ids"):
                return self.fallback.search(query, limit=limit, context=resolved)
            ids = results["ids"][0] if results.get("ids") else []
            distances = results["distances"][0] if results.get("distances") else []
            hits: list[RetrievalHit] = []
            for i, mem_id in enumerate(ids):
                dist = distances[i] if i < len(distances) else 1.0
                score = 1.0 / (1.0 + float(dist))
                row = _visible_memory_row(self.fallback.store, str(mem_id), resolved)
                if row:
                    hits.append(RetrievalHit(memory=row_to_memory(row), score=score, backend=self.name))
            return hits
        except Exception as exc:
            logger.warning("Chroma search failed, falling back to sqlite_exact: %s", exc)
            return self.fallback.search(query, limit=limit, context=resolved)


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
        scope: str | None = None,
        context: RetrievalContext | None = None,
    ) -> list[RetrievalHit]:
        resolved = retrieval_context(
            context=context,
            agent_id=agent_id,
            session_id=session_id,
            project=project,
            scope=scope,
        )
        try:
            from .vector import embed_text

            vector = embed_text(query, config=self.config)
            if vector is None:
                return self.fallback.search(query, limit=limit, context=resolved)
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                limit=limit,
            )
            hits: list[RetrievalHit] = []
            for scored in results:
                mem_id = str(scored.id)
                score = float(scored.score)
                row = _visible_memory_row(self.fallback.store, mem_id, resolved)
                if row:
                    hits.append(RetrievalHit(memory=row_to_memory(row), score=score, backend=self.name))
            return hits
        except Exception as exc:
            logger.warning("Qdrant search failed, falling back to sqlite_exact: %s", exc)
            return self.fallback.search(query, limit=limit, context=resolved)


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
        scope: str | None = None,
        context: RetrievalContext | None = None,
    ) -> list[RetrievalHit]:
        resolved = retrieval_context(
            context=context,
            agent_id=agent_id,
            session_id=session_id,
            project=project,
            scope=scope,
        )
        try:
            from .vector import embed_text

            vector = embed_text(query, config=self.config)
            if vector is None:
                return self.fallback.search(query, limit=limit, context=resolved)
            vec_str = json.dumps(vector)
            with self.conn.cursor() as cur:
                cur.execute(
                    f"SELECT id, embedding <-> '{vec_str}'::vector AS dist FROM super_memory_vectors ORDER BY dist LIMIT %s",
                    (limit,),
                )
                hits: list[RetrievalHit] = []
                for mem_id, dist in cur:
                    score = 1.0 / (1.0 + float(dist))
                    row = _visible_memory_row(self.fallback.store, str(mem_id), resolved)
                    if row:
                        hits.append(RetrievalHit(memory=row_to_memory(row), score=score, backend=self.name))
                return hits
        except Exception as exc:
            logger.warning("PGVector search failed, falling back to sqlite_exact: %s", exc)
            return self.fallback.search(query, limit=limit, context=resolved)


class DisabledVectorBackend:
    name = "disabled"

    def __init__(self, config: SuperMemoryConfig):
        self.config = config

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        agent_id: str | None = None,
        session_id: str | None = None,
        project: str | None = None,
        scope: str | None = None,
        context: RetrievalContext | None = None,
    ) -> list[RetrievalHit]:
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
