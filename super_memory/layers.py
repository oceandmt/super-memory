from __future__ import annotations

import json
import sqlite3
import hashlib
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from .models import MemoryLayer, MemoryRecord, SaveResult, SuperMemoryConfig
from .schema import PalaceHall


class MemoryBackend(ABC):
    layer: MemoryLayer

    @abstractmethod
    def save(self, record: MemoryRecord) -> SaveResult: ...

    @abstractmethod
    def recall(self, query: str, limit: int = 10) -> list[MemoryRecord]: ...


class WorkspaceMarkdownBackend(MemoryBackend):
    layer = MemoryLayer.WORKSPACE_MARKDOWN

    def __init__(self, config: SuperMemoryConfig):
        self.config = config
        self.root = Path(config.workspace_root)

    def save(self, record: MemoryRecord) -> SaveResult:
        mem_dir = self.root / self.config.daily_memory_dir
        mem_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now().strftime("%Y-%m-%d")
        path = mem_dir / f"{day}.md"
        lane = record.metadata.get("lane", record.source or "super-memory")
        line = (
            f"- {datetime.now().strftime('%H:%M')} [{lane}] "
            f"super-memory/{record.type.value}/{record.scope.value}: {record.content} "
            f"(id={record.id}; tags={', '.join(record.normalized_tags())})\n"
        )
        if not path.exists():
            path.write_text(f"# {day}\n\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        return SaveResult(layer=self.layer, ok=True, reference=str(path))

    def recall(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        # Canonical recall should normally use OpenClaw memory_search/Meili.
        # This fallback is intentionally simple and exact/local.
        hits: list[MemoryRecord] = []
        mem_dir = self.root / self.config.daily_memory_dir
        if not mem_dir.exists():
            return hits
        q = query.lower()
        for path in sorted(mem_dir.glob("*.md"), reverse=True):
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if q in line.lower():
                    hits.append(MemoryRecord(content=line, source=str(path), metadata={"layer": self.layer.value}))
                    if len(hits) >= limit:
                        return hits
        return hits


_DB_INIT_LOCK = threading.Lock()
_DB_INIT_DONE: set[str] = set()

class SQLiteLayerBackend(MemoryBackend):
    """Local deterministic adapter for MemPalace/Honcho/NeuralMemory-style layers.

    This keeps super-memory runnable without Docker or mandatory embedded LLMs.
    Real upstream adapters can later subclass/replace this while preserving API.
    """

    def __init__(self, config: SuperMemoryConfig, layer: MemoryLayer):
        self.config = config
        self.layer = layer
        self.path = Path(config.workspace_root) / config.sqlite_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        db_key = str(self.path.resolve())
        with _DB_INIT_LOCK:
            if db_key in _DB_INIT_DONE:
                return
            # Use schema.sql as single source of truth for table definitions.
            # run_migrations() handles CREATE IF NOT EXISTS + additive ALTERs.
            from .migrations import run_migrations
            run_migrations(self.config)
            with self._connect() as conn:
                # FTS5 is not in schema.sql (virtual table, tool-specific)
                conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(id, layer, content, tags)")
                # Drop stale FTS triggers from previous schema versions to avoid
                # UPDATE/INSERT failures. App manages FTS explicitly via code.
                for _t_name in conn.execute('SELECT name FROM sqlite_master WHERE type="trigger" AND tbl_name="memories" AND name LIKE "memories_fts_%"').fetchall():
                    conn.execute(f'DROP TRIGGER IF EXISTS {_t_name["name"]}')
                # FTS table may have stale schema (only content column). Detect and recreate.
                try:
                    _fts_cols = {c[1] for c in conn.execute('PRAGMA table_info(memories_fts)').fetchall()}
                    if 'id' not in _fts_cols:
                        conn.execute('DROP TABLE memories_fts')
                        conn.execute('CREATE VIRTUAL TABLE memories_fts USING fts5(id, layer, content, tags)')
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE memories ADD COLUMN pending_canonical_sync INTEGER DEFAULT 0")
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
            _DB_INIT_DONE.add(db_key)

    def save(self, record: MemoryRecord) -> SaveResult:
        tags = record.normalized_tags()
        pending_sync = record.metadata.get("pending_canonical_sync", False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memories
                (id, layer, content, type, scope, agent_id, session_id, project, tags_json, source, trust_score, created_at, metadata_json, pending_canonical_sync, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    self.layer.value,
                    record.content,
                    record.type.value,
                    record.scope.value,
                    record.agent_id,
                    record.session_id,
                    record.project,
                    json.dumps(tags, ensure_ascii=False),
                    record.source,
                    record.trust_score,
                    record.created_at.isoformat(),
                    json.dumps(record.metadata, ensure_ascii=False),
                    1 if pending_sync else 0,
                    record.metadata.get("content_hash"),
                ),
            )
            # FTS maintenance is handled by migrations-created triggers.  Older
            # databases used a standalone memories_fts(id, layer, content, tags)
            # table; current DBs use content-table form memories_fts(content,
            # content=memories, content_rowid=rowid).  Avoid manual writes here
            # so the save path remains compatible with both schemas and does not
            # break English FTS after a rebuild.
            if self.layer == MemoryLayer.MEMPALACE:
                self._save_palace_projection(conn, record, tags)
            elif self.layer == MemoryLayer.HONCHO:
                self._save_honcho_projection(conn, record)
            elif self.layer == MemoryLayer.NEURAL_MEMORY:
                self._save_graph_projection(conn, record)
        return SaveResult(layer=self.layer, ok=True, reference=f"sqlite://{self.path}#{self.layer.value}:{record.id}")

    def _save_palace_projection(self, conn: sqlite3.Connection, record: MemoryRecord, tags: list[str]) -> None:
        project = record.project or "general"
        wing = record.metadata.get("wing") or f"project:{project}"
        room = record.metadata.get("room") or record.session_id or record.type.value
        hall = record.metadata.get("hall") or _hall_for_type(record.type.value).value
        checksum = hashlib.sha256(f"{wing}\0{room}\0{hall}\0{record.content}".encode("utf-8")).hexdigest()
        conn.execute(
            """
            INSERT OR IGNORE INTO palace_drawers
            (id, memory_id, wing, room, hall, content, checksum, source, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"drawer:{record.id}",
                record.id,
                wing,
                room,
                hall,
                record.content,
                checksum,
                record.source,
                json.dumps({**record.metadata, "tags": tags}, ensure_ascii=False),
                record.created_at.isoformat(),
            ),
        )

    def _save_honcho_projection(self, conn: sqlite3.Connection, record: MemoryRecord) -> None:
        observer = record.agent_id
        observed = record.metadata.get("observed_peer_id") or record.metadata.get("peer_id") or "boss"
        workspace = record.metadata.get("workspace") or "openclaw"
        conn.execute(
            """
            INSERT OR REPLACE INTO honcho_events
            (id, memory_id, workspace, session_id, observer_peer_id, observed_peer_id, content, source, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"event:{record.id}",
                record.id,
                workspace,
                record.session_id,
                observer,
                observed,
                record.content,
                record.source,
                json.dumps(record.metadata, ensure_ascii=False),
                record.created_at.isoformat(),
            ),
        )

    def _save_graph_projection(self, conn: sqlite3.Connection, record: MemoryRecord) -> None:
        for target in record.metadata.get("related_memory_ids", []):
            conn.execute(
                """
                INSERT OR REPLACE INTO graph_edges
                (id, source_memory_id, target_memory_id, relation, weight, confidence, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"edge:{record.id}:{target}",
                    record.id,
                    target,
                    record.metadata.get("relation", "related_to"),
                    float(record.metadata.get("weight", 0.75)),
                    record.trust_score,
                    json.dumps(record.metadata, ensure_ascii=False),
                    record.created_at.isoformat(),
                ),
            )

    @staticmethod
    def _fts_safe_query(raw: str) -> str:
        """Escape special FTS characters so they don't break MATCH parsing.
        Falls back to LIKE-compatible plain text if needed.
        """
        for ch in ('"', '*', ':', '(', ')', '+', '-', '~', '<', '>', '!'):
            if ch in raw:
                raw = raw.replace(ch, ' ')
        raw = raw.strip()
        if not raw:
            return ''
        # If query looks like it might be an FTS operator, wrap each word as literal
        tokens = raw.split()
        safe = ' '.join(f'"{t}"' for t in tokens if t and t.upper() not in ('NEAR', 'AND', 'OR', 'NOT'))
        return safe or raw

    def recall(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        fts_query = self._fts_safe_query(query)
        out: list[MemoryRecord] = []
        with self._connect() as conn:
            try:
                if fts_query:
                    rows = conn.execute(
                        """
                        SELECT m.* FROM memories_fts f
                        JOIN memories m ON m.rowid = f.rowid
                        WHERE f.memories_fts MATCH ? AND m.layer = ?
                          AND COALESCE(json_extract(m.metadata_json, '$.soft_deleted'), 0) != 1
                        ORDER BY rank LIMIT ?
                        """,
                        (fts_query, self.layer.value, limit),
                    ).fetchall()
                    # Some live DBs had an empty/stale memories_fts after migration.
                    # Fall back to tokenized LIKE so recall_arbitrate_v3 still works.
                    if not rows:
                        terms = [t for t in query.split() if len(t) > 2][:6]
                        if terms:
                            where = " AND ".join(["content LIKE ?" for _ in terms])
                            rows = conn.execute(
                                f"""
                                SELECT * FROM memories
                                WHERE layer = ? AND COALESCE(json_extract(metadata_json, '$.soft_deleted'), 0) != 1
                                  AND {where}
                                ORDER BY created_at DESC LIMIT ?
                                """,
                                (self.layer.value, *[f"%{t}%" for t in terms], limit),
                            ).fetchall()
                else:
                    rows = []
            except sqlite3.OperationalError:
                # FTS parse failed — fall back to LIKE search
                rows = conn.execute(
                    """
                    SELECT * FROM memories
                    WHERE content LIKE ? AND layer = ?
                    LIMIT ?
                    """,
                    (f"%{query}%", self.layer.value, limit),
                ).fetchall()
            for row in rows:
                out.append(
                    MemoryRecord(
                        id=row["id"],
                        content=row["content"],
                        type=row["type"],
                        scope=row["scope"],
                        agent_id=row["agent_id"],
                        session_id=row["session_id"],
                        project=row["project"],
                        tags=json.loads(row["tags_json"]),
                        source=row["source"],
                        trust_score=row["trust_score"],
                        created_at=datetime.fromisoformat(row["created_at"]),
                        metadata=json.loads(row["metadata_json"]),
                    )
                )
        return out
        for row in rows:
            out.append(
                MemoryRecord(
                    id=row["id"],
                    content=row["content"],
                    type=row["type"],
                    scope=row["scope"],
                    agent_id=row["agent_id"],
                    session_id=row["session_id"],
                    project=row["project"],
                    tags=json.loads(row["tags_json"]),
                    source=row["source"],
                    trust_score=row["trust_score"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    metadata=json.loads(row["metadata_json"]),
                )
            )
        return out


def _hall_for_type(memory_type: str) -> PalaceHall:
    mapping = {
        "fact": PalaceHall.FACTS,
        "event": PalaceHall.EVENTS,
        "decision": PalaceHall.DISCOVERIES,
        "insight": PalaceHall.DISCOVERIES,
        "preference": PalaceHall.PREFERENCES,
        "workflow": PalaceHall.WORKFLOWS,
        "blocker": PalaceHall.BLOCKERS,
        "lesson": PalaceHall.LESSONS,
    }
    return mapping.get(memory_type, PalaceHall.FACTS)
