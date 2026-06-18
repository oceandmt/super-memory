from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import MemoryRecord, SuperMemoryConfig
from .storage import SuperMemoryStore, row_to_memory


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
    conformance target for future Chroma/Qdrant/pgvector implementations.
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
            # simple exact score: content match > tag-only match > recency fallback
            score = 1.0 if query and query.lower() in content.lower() else 0.5
            hits.append(RetrievalHit(memory=row_to_memory(row), score=score, backend=self.name))
        return hits


class ChromaBackend:
    """Optional Chroma backend facade.

    This skeleton keeps the interface stable. If chromadb is unavailable, it
    raises a clear RuntimeError and callers can fall back to sqlite_exact.
    """

    name = "chroma"

    def __init__(self, config: SuperMemoryConfig):
        try:
            import chromadb  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("chromadb is not installed; use sqlite_exact or install chromadb") from exc
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
        # Initial skeleton: keep filter semantics correct through sqlite_exact
        # until indexing is wired into the save lifecycle.
        return self.fallback.search(query, limit=limit, agent_id=agent_id, session_id=session_id, project=project)


class DisabledVectorBackend:
    name = "disabled"

    def __init__(self, config: SuperMemoryConfig):
        self.config = config

    def search(self, query: str, *, limit: int = 10, agent_id: str | None = None, session_id: str | None = None, project: str | None = None) -> list[RetrievalHit]:
        return []


def get_retrieval_backend(name: str | None, config: SuperMemoryConfig) -> RetrievalBackend:
    backend = (name or "sqlite_exact").strip().lower()
    if backend in {"sqlite", "sqlite_exact", "exact"}:
        return SQLiteExactBackend(config)
    if backend == "chroma":
        return ChromaBackend(config)
    if backend in {"disabled", "none"}:
        return DisabledVectorBackend(config)
    raise ValueError(f"unsupported retrieval backend: {name}")
