"""Knowledge Graph — entity nodes + typed relationships with temporal validity.

SQLite-backed temporal knowledge graph for MemPalace.
Links entities through typed relationships with time-bounded validity.

Relationship types:
  - works_on: entity works on a project
  - owns: entity owns a resource
  - created: entity created something
  - reviewed: entity reviewed something
  - mentioned_in: entity mentioned in context
  - part_of: entity is part of another
  - depends_on: entity depends on another
  - collaborates_with: entities collaborate

Usage:
    from super_memory.mempalace.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph(db_path)
    kg.add_entity("Lucas", kind="agent")
    kg.add_relationship("Lucas", "super-memory", "works_on")
    result = kg.query_entity("Lucas")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# ── Table schemas ───────────────────────────────────────────────────────────

KG_DDL = """
CREATE TABLE IF NOT EXISTS kg_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'unknown',
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS kg_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    strength REAL NOT NULL DEFAULT 1.0,
    valid_from TEXT,
    valid_until TEXT,
    source_drawer_id TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_entity) REFERENCES kg_entities(name),
    FOREIGN KEY (target_entity) REFERENCES kg_entities(name)
);

CREATE INDEX IF NOT EXISTS idx_kg_rel_source ON kg_relationships(source_entity);
CREATE INDEX IF NOT EXISTS idx_kg_rel_target ON kg_relationships(target_entity);
CREATE INDEX IF NOT EXISTS idx_kg_rel_type ON kg_relationships(rel_type);
CREATE INDEX IF NOT EXISTS idx_kg_rel_valid ON kg_relationships(valid_from, valid_until);

CREATE TABLE IF NOT EXISTS kg_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    source_drawer_id TEXT,
    valid_from TEXT,
    valid_until TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kg_facts_subject ON kg_facts(subject);
CREATE INDEX IF NOT EXISTS idx_kg_facts_predicate ON kg_facts(predicate);
"""


class KnowledgeGraph:
    """SQLite-backed temporal knowledge graph.

    Supports:
      - Entity CRUD with typed kinds
      - Relationship edges with temporal validity and provenance
      - Fact triples (subject, predicate, object) with confidence
      - Temporal queries (facts valid at a point in time)
      - Graph traversal from entity
    """

    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        self._ensure_schema()

    def _connect(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(KG_DDL)
            conn.commit()
        finally:
            conn.close()

    # ── Entities ────────────────────────────────────────────────────────

    def add_entity(self, name: str, kind: str = "unknown", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Add or update an entity node."""
        import json
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO kg_entities (name, kind, metadata_json, updated_at)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(name) DO UPDATE SET
                   kind = excluded.kind,
                   metadata_json = excluded.metadata_json,
                   updated_at = datetime('now')""",
                (name.strip(), kind, json.dumps(metadata or {}, ensure_ascii=False)),
            )
            conn.commit()
            return {"ok": True, "name": name, "kind": kind}
        finally:
            conn.close()

    def get_entity(self, name: str) -> dict[str, Any] | None:
        """Get entity by name."""
        import json
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM kg_entities WHERE name = ?", (name.strip(),)
            ).fetchone()
            if not row:
                return None
            return {
                "name": row["name"],
                "kind": row["kind"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        finally:
            conn.close()

    def list_entities(self, kind: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """List all entities, optionally filtered by kind."""
        import json
        conn = self._connect()
        try:
            if kind:
                rows = conn.execute(
                    "SELECT * FROM kg_entities WHERE kind = ? ORDER BY name LIMIT ?",
                    (kind, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM kg_entities ORDER BY name LIMIT ?",
                    (limit,),
                ).fetchall()
            return [
                {
                    "name": row["name"],
                    "kind": row["kind"],
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    # ── Relationships ───────────────────────────────────────────────────

    def add_relationship(
        self,
        source: str,
        target: str,
        rel_type: str,
        strength: float = 1.0,
        valid_from: str | None = None,
        valid_until: str | None = None,
        source_drawer_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a typed relationship between two entities.

        Args:
            source: Source entity name
            target: Target entity name
            rel_type: Relationship type (works_on, owns, created, etc.)
            strength: Relationship strength (0-1)
            valid_from: ISO datetime when relationship became valid
            valid_until: ISO datetime when relationship expires
            source_drawer_id: Provenance link to drawer
            metadata: Additional metadata
        """
        import json
        conn = self._connect()
        try:
            # Ensure both entities exist
            for name in (source, target):
                existing = conn.execute(
                    "SELECT 1 FROM kg_entities WHERE name = ?", (name.strip(),)
                ).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO kg_entities (name, kind) VALUES (?, 'unknown')",
                        (name.strip(),),
                    )

            conn.execute(
                """INSERT INTO kg_relationships 
                   (source_entity, target_entity, rel_type, strength, valid_from, valid_until, source_drawer_id, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source.strip(), target.strip(), rel_type,
                    strength, valid_from, valid_until,
                    source_drawer_id,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
            return {"ok": True, "source": source, "target": target, "rel_type": rel_type}
        finally:
            conn.close()

    def query_entity(
        self,
        name: str,
        direction: str = "both",
        rel_type: str | None = None,
        valid_at: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Query all relationships for an entity.

        Args:
            name: Entity name
            direction: "source" (outgoing), "target" (incoming), or "both"
            rel_type: Optional filter by relationship type
            valid_at: ISO datetime — only return relationships valid at this time

        Returns:
            Dict with entity info and relationships list
        """
        import json
        conn = self._connect()
        try:
            entity = self.get_entity(name)
            if not entity:
                return {"error": f"Entity not found: {name}", "entity": None, "relationships": []}

            relations: list[dict[str, Any]] = []

            if direction in ("source", "both"):
                where_parts = ["source_entity = ?"]
                params: list[Any] = [name.strip()]
                if rel_type:
                    where_parts.append("rel_type = ?")
                    params.append(rel_type)
                if valid_at:
                    where_parts.append("(valid_from IS NULL OR valid_from <= ?)")
                    where_parts.append("(valid_until IS NULL OR valid_until >= ?)")
                    params.extend([valid_at, valid_at])

                rows = conn.execute(
                    f"SELECT * FROM kg_relationships WHERE {' AND '.join(where_parts)} ORDER BY strength DESC LIMIT ?",
                    params + [limit],
                ).fetchall()
                for row in rows:
                    relations.append({
                        "direction": "outgoing",
                        "target": row["target_entity"],
                        "rel_type": row["rel_type"],
                        "strength": row["strength"],
                        "valid_from": row["valid_from"],
                        "valid_until": row["valid_until"],
                        "source_drawer_id": row["source_drawer_id"],
                        "metadata": json.loads(row["metadata_json"] or "{}"),
                    })

            if direction in ("target", "both"):
                where_parts = ["target_entity = ?"]
                params = [name.strip()]
                if rel_type:
                    where_parts.append("rel_type = ?")
                    params.append(rel_type)
                if valid_at:
                    where_parts.append("(valid_from IS NULL OR valid_from <= ?)")
                    where_parts.append("(valid_until IS NULL OR valid_until >= ?)")
                    params.extend([valid_at, valid_at])

                rows = conn.execute(
                    f"SELECT * FROM kg_relationships WHERE {' AND '.join(where_parts)} ORDER BY strength DESC LIMIT ?",
                    params + [limit],
                ).fetchall()
                for row in rows:
                    relations.append({
                        "direction": "incoming",
                        "source": row["source_entity"],
                        "rel_type": row["rel_type"],
                        "strength": row["strength"],
                        "valid_from": row["valid_from"],
                        "valid_until": row["valid_until"],
                        "source_drawer_id": row["source_drawer_id"],
                        "metadata": json.loads(row["metadata_json"] or "{}"),
                    })

            return {
                "entity": entity,
                "relationships": relations,
                "count": len(relations),
            }
        finally:
            conn.close()

    # ── Facts ────────────────────────────────────────────────────────────

    def add_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        source_drawer_id: str | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
    ) -> dict[str, Any]:
        """Add a fact triple (subject, predicate, object)."""
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO kg_facts (subject, predicate, object, confidence, source_drawer_id, valid_from, valid_until)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (subject.strip(), predicate.strip(), obj.strip(),
                 confidence, source_drawer_id, valid_from, valid_until),
            )
            conn.commit()
            return {"ok": True, "subject": subject, "predicate": predicate, "object": obj}
        finally:
            conn.close()

    def query_facts(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        obj: str | None = None,
        valid_at: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query facts with optional filters."""
        conn = self._connect()
        try:
            where_parts: list[str] = []
            params: list[Any] = []

            if subject:
                where_parts.append("subject = ?")
                params.append(subject.strip())
            if predicate:
                where_parts.append("predicate = ?")
                params.append(predicate.strip())
            if obj:
                where_parts.append("object = ?")
                params.append(obj.strip())
            if min_confidence > 0:
                where_parts.append("confidence >= ?")
                params.append(min_confidence)
            if valid_at:
                where_parts.append("(valid_from IS NULL OR valid_from <= ?)")
                where_parts.append("(valid_until IS NULL OR valid_until >= ?)")
                params.extend([valid_at, valid_at])

            where_clause = " AND ".join(where_parts) if where_parts else "1=1"

            rows = conn.execute(
                f"SELECT * FROM kg_facts WHERE {where_clause} ORDER BY confidence DESC LIMIT ?",
                params + [limit],
            ).fetchall()

            return [
                {
                    "subject": row["subject"],
                    "predicate": row["predicate"],
                    "object": row["object"],
                    "confidence": row["confidence"],
                    "valid_from": row["valid_from"],
                    "valid_until": row["valid_until"],
                    "source_drawer_id": row["source_drawer_id"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def stats(self) -> dict[str, Any]:
        """Get knowledge graph statistics."""
        conn = self._connect()
        try:
            entity_count = conn.execute("SELECT COUNT(*) as c FROM kg_entities").fetchone()["c"]
            rel_count = conn.execute("SELECT COUNT(*) as c FROM kg_relationships").fetchone()["c"]
            fact_count = conn.execute("SELECT COUNT(*) as c FROM kg_facts").fetchone()["c"]
            return {
                "entities": entity_count,
                "relationships": rel_count,
                "facts": fact_count,
            }
        finally:
            conn.close()
