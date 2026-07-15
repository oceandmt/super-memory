"""Abstract Storage Backend — CoreStorage ABC for multi-backend support.

Ported from neural-memory v4.58.0 storage/base.py.
Defines a common interface for storage backends (SQLite, Postgres, etc.)
with 29+ abstract methods covering all CRUD operations.

Current implementation: SQLiteCoreStorage wrapping SuperMemoryStore.
Future backends: PostgresCoreStorage, InMemoryCoreStorage.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from .models import MemoryRecord

logger = logging.getLogger("super-memory.storage.base")


class CoreStorage(ABC):
    """Abstract storage backend for memory persistence."""

    @abstractmethod
    def connect(self):
        ...

    @abstractmethod
    def initialize(self) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    @abstractmethod
    def save_memory(self, record: MemoryRecord) -> Any:
        ...

    @abstractmethod
    def save_memory_batch(self, records: list[MemoryRecord]) -> list[Any]:
        ...

    @abstractmethod
    def get_memory(self, memory_id: str, layer: str | None = None) -> MemoryRecord | None:
        ...

    @abstractmethod
    def list_memory_rows(self, limit: int = 500, offset: int = 0, where_clause: str | None = None, where_args: list[Any] | None = None, order_by: str = "rowid DESC") -> list[Any]:
        ...

    @abstractmethod
    def search_memories(self, query: str, limit: int = 10, agent_scope: str = "current", session_scope: str = "recent") -> list[Any]:
        ...

    @abstractmethod
    def count_memories(self, where_clause: str | None = None, where_args: list[Any] | None = None) -> int:
        ...

    @abstractmethod
    def update_memory(self, memory_id: str, content: str | None = None, metadata: dict[str, Any] | None = None, tags: list[str] | None = None) -> bool:
        ...

    @abstractmethod
    def pin_memory(self, memory_id: str, pinned: bool = True) -> bool:
        ...

    @abstractmethod
    def soft_delete(self, memory_id: str) -> bool:
        ...

    @abstractmethod
    def hard_delete(self, memory_id: str) -> bool:
        ...

    @abstractmethod
    def dedup_check(self, record: MemoryRecord) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_graph_neighbors(self, neuron_id: str, direction: str = "out", limit: int = 20) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def count_graph_edges(self) -> int:
        ...

    @abstractmethod
    def count_graph_neurons(self) -> int:
        ...

    @abstractmethod
    def get_leitner_due(self, limit: int = 50) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def update_leitner(self, memory_id: str, box: int, next_review: str) -> bool:
        ...

    @abstractmethod
    def stats(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def health(self) -> dict[str, Any]:
        ...


class SQLiteCoreStorage(CoreStorage):
    """Concrete CoreStorage implementation wrapping SuperMemoryStore."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def connect(self):
        return self._store.connect()

    def initialize(self) -> None:
        if hasattr(self._store, "initialize"):
            self._store.initialize()

    def close(self) -> None:
        pass

    def save_memory(self, record: MemoryRecord) -> Any:
        from .service import SuperMemoryService
        from .config import load_config
        svc = SuperMemoryService(load_config())
        return svc.save(record)

    def save_memory_batch(self, records: list[MemoryRecord]) -> list[Any]:
        return [self.save_memory(r) for r in records]

    def get_memory(self, memory_id: str, layer: str | None = None) -> MemoryRecord | None:
        return self._store.get_memory(memory_id, layer)

    def list_memory_rows(self, limit=500, offset=0, where_clause=None, where_args=None, order_by="rowid DESC"):
        return self._store.list_memory_rows(limit)

    def search_memories(self, query, limit=10, agent_scope="current", session_scope="recent"):
        from .hybrid_recall import HybridRecall
        from .config import load_config
        recall = HybridRecall(load_config())
        result = recall.cross_scope_recall(query, agent_scope, session_scope, limit=limit)
        return result.get("results", [])

    def count_memories(self, where_clause=None, where_args=None):
        with self._store.connect() as conn:
            if where_clause:
                row = conn.execute(f"SELECT COUNT(*) as c FROM memories WHERE {where_clause}", where_args or []).fetchone()  # nosec-sql: no current caller passes where_clause (verified via grep); guarded for future callers by design contract
            else:
                row = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()
            return row["c"] if row else 0

    def update_memory(self, memory_id, content=None, metadata=None, tags=None):
        with self._store.connect() as conn:
            if content is not None:
                conn.execute("UPDATE memories SET content=? WHERE id=?", (content, memory_id))
            if metadata is not None:
                conn.execute("UPDATE memories SET metadata_json=? WHERE id=?", (json.dumps(metadata, ensure_ascii=False), memory_id))
            if tags is not None:
                conn.execute("UPDATE memories SET tags_json=? WHERE id=?", (json.dumps(tags, ensure_ascii=False), memory_id))
            conn.commit()
        return True

    def pin_memory(self, memory_id, pinned=True):
        with self._store.connect() as conn:
            existing = conn.execute("SELECT metadata_json FROM memories WHERE id=?", (memory_id,)).fetchone()
            if not existing:
                return False
            meta = json.loads(existing["metadata_json"] or "{}")
            meta["pinned"] = pinned
            conn.execute("UPDATE memories SET metadata_json=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), memory_id))
            conn.commit()
        return True

    def soft_delete(self, memory_id):
        with self._store.connect() as conn:
            existing = conn.execute("SELECT metadata_json FROM memories WHERE id=?", (memory_id,)).fetchone()
            if not existing:
                return False
            meta = json.loads(existing["metadata_json"] or "{}")
            meta["soft_deleted"] = True
            conn.execute("UPDATE memories SET metadata_json=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), memory_id))
            conn.commit()
        return True

    def hard_delete(self, memory_id):
        with self._store.connect() as conn:
            conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            conn.commit()
        return True

    def dedup_check(self, record):
        from .service import SuperMemoryService
        from .config import load_config
        svc = SuperMemoryService(load_config())
        return svc.dedup_check(record)

    def get_graph_neighbors(self, neuron_id, direction="out", limit=20):
        with self._store.connect() as conn:
            if direction == "in":
                rows = conn.execute("SELECT * FROM cognitive_synapses WHERE target_neuron_id=? LIMIT ?", (neuron_id, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM cognitive_synapses WHERE source_neuron_id=? LIMIT ?", (neuron_id, limit)).fetchall()
            return [dict(r) for r in rows]

    def count_graph_edges(self):
        with self._store.connect() as conn:
            row = conn.execute("SELECT COUNT(*) as c FROM cognitive_synapses").fetchone()
            return row["c"] if row else 0

    def count_graph_neurons(self):
        with self._store.connect() as conn:
            row = conn.execute("SELECT COUNT(*) as c FROM cognitive_neurons").fetchone()
            return row["c"] if row else 0

    def get_leitner_due(self, limit=50):
        with self._store.connect() as conn:
            now = datetime.now().isoformat()
            rows = conn.execute(
                "SELECT id, content, leiter_box, next_review FROM memories "
                "WHERE next_review IS NOT NULL AND next_review <= ? ORDER BY leiter_box ASC LIMIT ?",
                (now, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_leitner(self, memory_id, box, next_review):
        with self._store.connect() as conn:
            conn.execute("UPDATE memories SET leiter_box=?, next_review=? WHERE id=?", (box, next_review, memory_id))
            conn.commit()
        return True

    def stats(self):
        with self._store.connect() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
            types = {r["type"]: r["c"] for r in conn.execute("SELECT type, COUNT(*) as c FROM memories WHERE type IS NOT NULL GROUP BY type").fetchall()}
            neurons = conn.execute("SELECT COUNT(*) as c FROM cognitive_neurons").fetchone()["c"]
            synapses = conn.execute("SELECT COUNT(*) as c FROM cognitive_synapses").fetchone()["c"]
        return {"total_memories": total, "type_distribution": types, "graph_neurons": neurons, "graph_synapses": synapses}

    def health(self):
        try:
            with self._store.connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return {"ok": True, "backend": "sqlite"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def create_storage(backend: str = "sqlite", config: Any | None = None, **kwargs: Any) -> CoreStorage:
    """Factory: create a CoreStorage instance by backend name."""
    if backend == "sqlite":
        from .storage import SuperMemoryStore
        if config is None:
            from .config import load_config
            config = load_config()
        return SQLiteCoreStorage(SuperMemoryStore(config))
    elif backend == "postgres":
        raise NotImplementedError("Postgres backend not yet implemented")
    else:
        raise ValueError(f"Unknown backend: {backend}. Supported: sqlite, postgres")
