from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .config import load_config
from .models import MemoryRecord
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory

NEURON_TYPES = {"memory", "entity", "concept", "tag", "project", "type", "scope"}
SYNAPSE_TYPES = {"anchors", "mentions", "tagged", "in_project", "is_type", "in_scope", "related_to", "evidence_for", "evidence_against", "predicted", "verified_by", "falsified_by"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store(config_path: str | None = None) -> SuperMemoryStore:
    cfg = load_config(config_path)
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    init_tables(store)
    return store


def init_tables(store: SuperMemoryStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_neurons (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                source_memory_id TEXT,
                confidence REAL NOT NULL DEFAULT 0.5,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cognitive_neurons_kind ON cognitive_neurons(kind)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cognitive_neurons_source ON cognitive_neurons(source_memory_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_synapses (
                id TEXT PRIMARY KEY,
                source_neuron_id TEXT NOT NULL,
                target_neuron_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 0.5,
                confidence REAL NOT NULL DEFAULT 0.5,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source_neuron_id, target_neuron_id, relation)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cognitive_synapses_source ON cognitive_synapses(source_neuron_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cognitive_synapses_target ON cognitive_synapses(target_neuron_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_fibers (
                id TEXT PRIMARY KEY,
                anchor_neuron_id TEXT NOT NULL,
                neuron_ids_json TEXT NOT NULL,
                synapse_ids_json TEXT NOT NULL,
                pathway_json TEXT NOT NULL,
                salience REAL NOT NULL DEFAULT 0.5,
                coherence REAL NOT NULL DEFAULT 0.5,
                conductivity REAL NOT NULL DEFAULT 1.0,
                frequency INTEGER NOT NULL DEFAULT 0,
                summary TEXT,
                tags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cognitive_fibers_anchor ON cognitive_fibers(anchor_neuron_id)")


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def _safe_token(text: str, max_len: int = 48) -> str:
    token = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", text.strip().lower()).strip("-")[:max_len]
    return token or "empty"


def _upsert_neuron(conn: Any, *, kind: str, content: str, source_memory_id: str | None = None, confidence: float = 0.5, metadata: dict[str, Any] | None = None) -> str:
    kind = kind if kind in NEURON_TYPES else "concept"
    neuron_id = f"n:{kind}:{_safe_token(content)}:{_hash(kind + ':' + content)[:12]}"
    now = _now()
    conn.execute(
        """
        INSERT INTO cognitive_neurons (id, kind, content, content_hash, source_memory_id, confidence, metadata_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          confidence=max(confidence, excluded.confidence),
          metadata_json=excluded.metadata_json,
          updated_at=excluded.updated_at
        """,
        (neuron_id, kind, content, _hash(content), source_memory_id, max(0.0, min(1.0, confidence)), json.dumps(metadata or {}, ensure_ascii=False), now, now),
    )
    return neuron_id


def _upsert_synapse(conn: Any, *, source: str, target: str, relation: str, weight: float = 0.5, confidence: float = 0.5, metadata: dict[str, Any] | None = None) -> str:
    relation = relation if relation in SYNAPSE_TYPES else "related_to"
    synapse_id = f"s:{_hash(source + '>' + relation + '>' + target)[:24]}"
    now = _now()
    conn.execute(
        """
        INSERT INTO cognitive_synapses (id, source_neuron_id, target_neuron_id, relation, weight, confidence, metadata_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_neuron_id, target_neuron_id, relation) DO UPDATE SET
          weight=max(weight, excluded.weight),
          confidence=max(confidence, excluded.confidence),
          metadata_json=excluded.metadata_json,
          updated_at=excluded.updated_at
        """,
        (synapse_id, source, target, relation, max(0.0, min(1.0, weight)), max(0.0, min(1.0, confidence)), json.dumps(metadata or {}, ensure_ascii=False), now, now),
    )
    return synapse_id


def _entity_terms(record: MemoryRecord) -> list[str]:
    terms: list[str] = []
    if record.project:
        terms.append(record.project)
    terms.extend([t for t in record.normalized_tags() if not t.startswith("agent:")])
    # Deterministic lightweight entity extraction: TitleCase/acronyms plus exact identifiers.
    for match in re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b|\b[a-z][a-z0-9_]+(?:[-_.][a-z0-9_]+)+\b|/[a-zA-Z0-9_./-]+|[a-zA-Z0-9_.-]+\([^)]*\)", record.content):
        terms.append(match)
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        term = str(term).strip()[:120]
        if term and term.lower() not in seen:
            seen.add(term.lower())
            out.append(term)
    return out[:24]


def project_memory(record: MemoryRecord, config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    with store.connect() as conn:
        anchor = _upsert_neuron(conn, kind="memory", content=record.content[:500], source_memory_id=record.id, confidence=record.trust_score or 0.65, metadata={"memory_id": record.id, "source": record.source})
        neurons = [anchor]
        synapses: list[str] = []
        type_n = _upsert_neuron(conn, kind="type", content=record.type.value, confidence=0.9)
        scope_n = _upsert_neuron(conn, kind="scope", content=record.scope.value, confidence=0.9)
        neurons.extend([type_n, scope_n])
        synapses.append(_upsert_synapse(conn, source=anchor, target=type_n, relation="is_type", weight=0.85, confidence=0.9))
        synapses.append(_upsert_synapse(conn, source=anchor, target=scope_n, relation="in_scope", weight=0.75, confidence=0.8))
        if record.project:
            project_n = _upsert_neuron(conn, kind="project", content=record.project, confidence=0.9)
            neurons.append(project_n)
            synapses.append(_upsert_synapse(conn, source=anchor, target=project_n, relation="in_project", weight=0.9, confidence=0.9))
        for term in _entity_terms(record):
            kind = "tag" if ":" in term and not term.startswith("/") else "entity"
            n = _upsert_neuron(conn, kind=kind, content=term, source_memory_id=record.id if kind == "entity" else None, confidence=record.trust_score or 0.6)
            neurons.append(n)
            synapses.append(_upsert_synapse(conn, source=anchor, target=n, relation="tagged" if kind == "tag" else "mentions", weight=0.65, confidence=record.trust_score or 0.6))
        for target in record.metadata.get("related_memory_ids", []) or []:
            target_n = _upsert_neuron(conn, kind="memory", content=f"memory:{target}", source_memory_id=str(target), confidence=record.trust_score or 0.55)
            neurons.append(target_n)
            synapses.append(_upsert_synapse(conn, source=anchor, target=target_n, relation=record.metadata.get("relation", "related_to"), weight=float(record.metadata.get("weight", 0.7)), confidence=record.trust_score or 0.55))
        neuron_ids = list(dict.fromkeys(neurons))
        synapse_ids = list(dict.fromkeys(synapses))
        fiber_id = f"f:{record.id}"
        now = _now()
        salience = 0.9 if record.type.value in {"decision", "workflow", "blocker", "doctrine", "lesson", "preference"} else 0.55
        coherence = min(1.0, 0.35 + len(synapse_ids) * 0.05)
        conn.execute(
            """
            INSERT OR REPLACE INTO cognitive_fibers
            (id, anchor_neuron_id, neuron_ids_json, synapse_ids_json, pathway_json, salience, coherence, conductivity, frequency, summary, tags_json, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT frequency FROM cognitive_fibers WHERE id=?), 0), ?, ?, ?, ?, ?)
            """,
            (
                fiber_id,
                anchor,
                json.dumps(neuron_ids, ensure_ascii=False),
                json.dumps(synapse_ids, ensure_ascii=False),
                json.dumps(neuron_ids[:12], ensure_ascii=False),
                salience,
                coherence,
                1.0,
                fiber_id,
                record.content[:280],
                json.dumps(record.normalized_tags(), ensure_ascii=False),
                json.dumps({"memory_id": record.id, "layer": "neural_memory_projection", "canonical_first": True}, ensure_ascii=False),
                record.created_at.isoformat(),
                now,
            ),
        )
    return {"ok": True, "memory_id": record.id, "fiber_id": fiber_id, "anchor_neuron_id": anchor, "neurons": len(neuron_ids), "synapses": len(synapse_ids)}


def stats(config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    with store.connect() as conn:
        neurons = conn.execute("SELECT kind, COUNT(*) c FROM cognitive_neurons GROUP BY kind").fetchall()
        synapses = conn.execute("SELECT relation, COUNT(*) c FROM cognitive_synapses GROUP BY relation").fetchall()
        fibers = conn.execute("SELECT COUNT(*) c FROM cognitive_fibers").fetchone()["c"]
    return {"ok": True, "neurons": {r["kind"]: r["c"] for r in neurons}, "synapses": {r["relation"]: r["c"] for r in synapses}, "fibers": fibers, "canonical_first": True}


def _bounded_limit(limit: int, default: int = 20, maximum: int = 500) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(maximum, value))

def neighbors(neuron_or_memory_id: str, direction: str = "out", limit: int = 20, config_path: str | None = None) -> dict[str, Any]:
    limit = _bounded_limit(limit)
    store = _store(config_path)
    with store.connect() as conn:
        node = conn.execute("SELECT id FROM cognitive_neurons WHERE id=? OR source_memory_id=? LIMIT 1", (neuron_or_memory_id, neuron_or_memory_id)).fetchone()
        if not node:
            return {"ok": True, "query": neuron_or_memory_id, "neighbors": []}
        node_id = node["id"]
        if direction == "in":
            rows = conn.execute("SELECT s.*, n.content target_content, n.kind target_kind FROM cognitive_synapses s JOIN cognitive_neurons n ON n.id=s.source_neuron_id WHERE s.target_neuron_id=? LIMIT ?", (node_id, limit)).fetchall()
        else:
            rows = conn.execute("SELECT s.*, n.content target_content, n.kind target_kind FROM cognitive_synapses s JOIN cognitive_neurons n ON n.id=s.target_neuron_id WHERE s.source_neuron_id=? LIMIT ?", (node_id, limit)).fetchall()
    return {"ok": True, "query": neuron_or_memory_id, "node_id": node_id, "neighbors": [{"synapse_id": r["id"], "relation": r["relation"], "weight": r["weight"], "confidence": r["confidence"], "target_content": r["target_content"], "target_kind": r["target_kind"]} for r in rows]}


def recall(query: str, limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    limit = _bounded_limit(limit, default=10)
    store = _store(config_path)
    q = f"%{query.lower()}%"
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT f.*, n.content anchor_content, n.source_memory_id
            FROM cognitive_fibers f
            JOIN cognitive_neurons n ON n.id=f.anchor_neuron_id
            WHERE lower(f.summary) LIKE ? OR lower(f.tags_json) LIKE ? OR lower(n.content) LIKE ?
            ORDER BY f.salience DESC, f.updated_at DESC LIMIT ?
            """,
            (q, q, q, limit),
        ).fetchall()
        for row in rows:
            conn.execute("UPDATE cognitive_fibers SET frequency=frequency+1, updated_at=? WHERE id=?", (_now(), row["id"]))
    return {"ok": True, "query": query, "fibers": [{"id": r["id"], "memory_id": json.loads(r["metadata_json"]).get("memory_id"), "anchor_neuron_id": r["anchor_neuron_id"], "summary": r["summary"], "salience": r["salience"], "coherence": r["coherence"], "frequency": r["frequency"] + 1, "tags": json.loads(r["tags_json"])} for r in rows]}


def rebuild(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    limit = _bounded_limit(limit, default=500, maximum=2000)
    store = _store(config_path)
    rows = store.list_memory_rows(limit=limit)
    projected = []
    seen: set[str] = set()
    for row in rows:
        rec = row_to_memory(row)
        if rec.id in seen:
            continue
        seen.add(rec.id)
        projected.append(project_memory(rec, config_path=config_path))
    return {"ok": True, "projected": len(projected), "items": projected[:20], "truncated": len(projected) > 20}


def cleanup_orphans(config_path: str | None = None) -> dict[str, Any]:
    store = _store(config_path)
    with store.connect() as conn:
        before = conn.execute("SELECT COUNT(*) c FROM cognitive_neurons").fetchone()["c"]
        conn.execute(
            """
            DELETE FROM cognitive_neurons
            WHERE source_memory_id IS NOT NULL
              AND source_memory_id NOT IN (SELECT DISTINCT id FROM memories)
            """
        )
        conn.execute("DELETE FROM cognitive_synapses WHERE source_neuron_id NOT IN (SELECT id FROM cognitive_neurons) OR target_neuron_id NOT IN (SELECT id FROM cognitive_neurons)")
        conn.execute("DELETE FROM cognitive_fibers WHERE anchor_neuron_id NOT IN (SELECT id FROM cognitive_neurons)")
        after = conn.execute("SELECT COUNT(*) c FROM cognitive_neurons").fetchone()["c"]
    return {"ok": True, "removed_neurons": before - after, "neurons_before": before, "neurons_after": after}

def rebuild_incremental(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    limit = _bounded_limit(limit, default=500, maximum=2000)
    store = _store(config_path)
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT m.* FROM memories m
            LEFT JOIN cognitive_fibers f ON f.id = 'f:' || m.id
            WHERE f.id IS NULL OR f.updated_at < m.created_at
            ORDER BY m.created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    projected = []
    for row in rows:
        projected.append(project_memory(row_to_memory(row), config_path=config_path))
    return {"ok": True, "projected": len(projected), "items": projected[:20], "truncated": len(projected) > 20}
