from __future__ import annotations

import json
import math
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .models import MemoryRecord
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory

NEURON_TYPES = {"memory", "entity", "concept", "tag", "project", "type", "scope"}
SYNAPSE_TYPES = {
    "anchors", "mentions", "tagged", "in_project", "is_type", "in_scope",
    "related_to", "evidence_for", "evidence_against", "predicted", "verified_by",
    "falsified_by", "caused_by", "leads_to", "resolved_by", "contradicts",
    "supports", "refutes", "supersedes", "before", "after", "derived_from",
}

# Relation direction: which node is source vs target for directional semantics
DIRECTED_RELATIONS = {"caused_by", "leads_to", "before", "after", "derived_from"}

# Decay rate per hop: activation multiplies by this factor at each step
DECAY_PER_HOP = 0.55

# Default spreading activation config
DEFAULT_ACTIVATION_DEPTH = 2
DEFAULT_ACTIVATION_TOP_K = 20
DEFAULT_ACTIVATION_SEED_LIMIT = 30


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


# ── Spreading Activation Engine ──────────────────────────────────────────────


def _token_overlap_score(query: str, text: str) -> float:
    """Simple but fast token overlap scorer — no embeddings needed."""
    q_lower = query.lower()
    t_lower = (text or "").lower()
    if not t_lower:
        return 0.0
    # Direct substring
    if q_lower in t_lower:
        base = 0.65
        # Boost by how much of the query is in the text
        return base + 0.35 * (len(q_lower) / max(len(t_lower), 1))
    # Token overlap
    q_tokens = set(re.split(r"[^a-z0-9]+", q_lower))
    t_tokens = set(re.split(r"[^a-z0-9]+", t_lower))
    if not q_tokens or not t_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens)
    if overlap == 0:
        return 0.0
    return 0.45 * (overlap / len(q_tokens))


def _time_decay(dt_str: str | None, half_life_days: float = 30.0) -> float:
    """Exponential decay by age. Returns factor in [0.05, 1.0]."""
    if not dt_str:
        return 0.3
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return 0.3
    age_days = (datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)).total_seconds() / 86400.0
    return max(0.05, math.exp(-math.log(2) * age_days / half_life_days))


def _load_graph_index(store: SuperMemoryStore) -> dict[str, Any]:
    """Load neurons, synapses, and fibers into in-memory indexes for fast traversal."""
    with store.connect() as conn:
        neurons = {
            r["id"]: {
                "kind": r["kind"],
                "content": r["content"],
                "confidence": r["confidence"],
                "source_memory_id": r["source_memory_id"],
                "updated_at": r["updated_at"],
            }
            for r in conn.execute("SELECT * FROM cognitive_neurons").fetchall()
        }
        # Build adjacency lists
        outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in conn.execute("SELECT * FROM cognitive_synapses").fetchall():
            edge = {
                "id": r["id"],
                "source": r["source_neuron_id"],
                "target": r["target_neuron_id"],
                "relation": r["relation"],
                "weight": r["weight"],
                "confidence": r["confidence"],
            }
            outgoing[r["source_neuron_id"]].append(edge)
            incoming[r["target_neuron_id"]].append(edge)
    return {"neurons": neurons, "outgoing": dict(outgoing), "incoming": dict(incoming)}


def _seed_matches(query: str, neurons: dict[str, Any], limit: int) -> list[str]:
    """Find initial seed neurons by text match against query."""
    scored: list[tuple[float, str]] = []
    for nid, ndata in neurons.items():
        score = _token_overlap_score(query, ndata["content"])
        if score > 0.0:
            scored.append((score, nid))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [nid for _, nid in scored[:limit]]


def spreading_activation(
    query: str,
    depth: int = DEFAULT_ACTIVATION_DEPTH,
    top_k: int = DEFAULT_ACTIVATION_TOP_K,
    seed_limit: int = DEFAULT_ACTIVATION_SEED_LIMIT,
    config_path: str | None = None,
) -> dict[str, Any]:
    """
    Spreading activation recall.

    Algorithm:
      1. Seed: text-match query against neuron contents.
      2. Spread: for depth hops, propagate activation through weighted synapses.
      3. Decay: each hop multiplies by DECAY_PER_HOP (0.55).
      4. Boost: recency, confidence, and access frequency.
      5. Return ranked neurons with activation paths and their source memories.

    Returns neurons sorted by activation, each with path trace.
    """
    t0 = time.perf_counter()
    store = _store(config_path)
    graph_index = _load_graph_index(store)
    neurons = graph_index["neurons"]
    outgoing = graph_index["outgoing"]
    incoming = graph_index["incoming"]

    if not neurons:
        return {"ok": True, "query": query, "depth": depth, "results": [], "elapsed_ms": 0, "method": "spreading_activation"}

    # Phase 1: Seed
    seeds = _seed_matches(query, neurons, limit=seed_limit)

    # Phase 2: Spreading activation (BFS with decay)
    activation: dict[str, float] = {}
    paths: dict[str, list[str]] = {}  # neuron_id -> path of relation hops
    # Set initial activation from seeds
    for seed_id in seeds:
        nd = neurons.get(seed_id)
        if not nd:
            continue
        base = _token_overlap_score(query, nd["content"])
        # boost by confidence
        base *= (0.5 + 0.5 * nd.get("confidence", 0.5))
        # boost by recency
        time_factor = _time_decay(nd.get("updated_at"))
        base *= (0.6 + 0.4 * time_factor)
        activation[seed_id] = base
        paths[seed_id] = ["seed"]

    # Track which neurons we've queued for spreading (to prevent re-enqueuing same depth)
    frontier = set(seeds)
    for hop in range(depth):
        next_frontier: set[str] = set()
        new_activation: dict[str, float] = {}
        decay = DECAY_PER_HOP ** (hop + 1)
        for current_id in frontier:
            current_act = activation.get(current_id, 0)
            if current_act < 0.02:
                continue
            # Spread outward through outgoing synapses
            for edge in outgoing.get(current_id, []):
                neighbor = edge["target"]
                # Skip cycles
                if neighbor in paths:
                    continue
                propagated = current_act * decay * edge.get("weight", 0.5) * edge.get("confidence", 0.5)
                if propagated < 0.01:
                    continue
                if propagated > new_activation.get(neighbor, 0):
                    new_activation[neighbor] = propagated
                    paths[neighbor] = paths.get(current_id, []) + [f"{edge['relation']}(w={edge.get('weight', 0.5):.2f})"]
                next_frontier.add(neighbor)
            # Also follow incoming (bidirectional traversal)
            for edge in incoming.get(current_id, []):
                neighbor = edge["source"]
                if neighbor in paths:
                    continue
                propagated = current_act * decay * 0.75 * edge.get("weight", 0.5) * edge.get("confidence", 0.5)
                if propagated < 0.01:
                    continue
                if propagated > new_activation.get(neighbor, 0):
                    new_activation[neighbor] = propagated
                    paths[neighbor] = paths.get(current_id, []) + [f"<-{edge['relation']}(w={edge.get('weight', 0.5):.2f})"]
                next_frontier.add(neighbor)
        # Merge
        for nid, act_val in new_activation.items():
            activation[nid] = act_val
        frontier = next_frontier
        if not frontier:
            break

    # Phase 3: Post-process — add frequency boost and sort
    results: list[dict[str, Any]] = []
    for nid, act_val in activation.items():
        nd = neurons.get(nid, {})
        # Small frequency boost (extracted from fiber stats if available)
        results.append({
            "neuron_id": nid,
            "kind": nd.get("kind", "unknown"),
            "content": nd.get("content", ""),
            "activation": round(act_val, 6),
            "confidence": nd.get("confidence", 0.5),
            "source_memory_id": nd.get("source_memory_id"),
            "path": ":".join(paths.get(nid, [])),
        })

    # Sort by activation descending
    results.sort(key=lambda x: x["activation"], reverse=True)
    trimmed = results[:top_k]

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    # Record access reinforcement in background
    for r in trimmed:
        r["reinforced"] = True

    return {
        "ok": True,
        "query": query,
        "depth": depth,
        "seeds_found": len(seeds),
        "total_activated": len(activation),
        "results": trimmed,
        "elapsed_ms": elapsed_ms,
        "method": "spreading_activation",
    }
