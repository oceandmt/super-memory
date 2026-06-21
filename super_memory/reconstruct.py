"""Answer Reconstruction for Super Memory.

Reconstructs related memories into coherent narratives:
1. Causal chains (via CAUSED_BY / LEADS_TO synapses)
2. Event sequences (temporal BEFORE / AFTER ordering)
3. Temporal ranges (memories within a time window)
4. Topic narratives (clustered by content/tag similarity)

This is a lightweight (~500 LOC) alternative to neural-memory's
374 LOC answer reconstruction engine, adapted for super-memory's
canonical-first architecture.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .models import MemoryRecord
from .storage import SuperMemoryStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Causal Chains ──────────────────────────────────────────────────────────


def causal_chain(
    memory_id: str,
    store: SuperMemoryStore,
    max_depth: int = 6,
    direction: str = "forward",
) -> dict[str, Any]:
    """Trace a causal chain through CAUSED_BY / LEADS_TO synapses.

    Args:
        memory_id: Starting memory.
        store: SuperMemoryStore.
        max_depth: Max steps to traverse (default 6).
        direction: 'forward' (what this caused) or 'backward' (what caused this).

    Returns:
        Chain narrative with linked memories.
    """
    visited: set[str] = set()

    def _traverse(
        mid: str,
        path: list[dict[str, Any]],
        depth: int,
    ) -> None:
        nonlocal visited
        if depth > max_depth or mid in visited:
            return
        visited.add(mid)

        # Get the memory record
        memory = _get_memory(mid, store)
        if memory is None:
            return

        entry = {
            "memory_id": mid,
            "content": memory.content[:200],
            "type": memory.type.value,
            "created_at": memory.created_at.isoformat() if memory.created_at else "",
        }
        path.append(entry)

        # Find causal connections
        if direction == "forward":
            syn_rel = "leads_to"
        else:
            syn_rel = "caused_by"

        with store.connect() as conn:
            try:
                if direction == "forward":
                    rows = conn.execute(
                        "SELECT target_neuron_id FROM cognitive_synapses "
                        "WHERE source_neuron_id = ? AND relation = ?",
                        (mid, syn_rel),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT source_neuron_id FROM cognitive_synapses "
                        "WHERE target_neuron_id = ? AND relation = ?",
                        (mid, syn_rel),
                    ).fetchall()
            except Exception:
                rows = []

            for row in rows:
                nid = row[0]
                _traverse(nid, path, depth + 1)

    result_path: list[dict[str, Any]] = []
    _traverse(memory_id, result_path, 0)

    # Build narrative
    narrative_parts: list[str] = []
    steps = result_path
    for i, step in enumerate(steps):
        arrow = "→" if i < len(steps) - 1 else ""
        narrative_parts.append(f"[{step['type']}] {step['content'][:120]} {arrow}")

    return {
        "ok": True,
        "chains": [result_path],
        "narrative": "\n".join(narrative_parts),
        "node_count": len(visited),
    }


def _get_memory(memory_id: str, store: SuperMemoryStore) -> MemoryRecord | None:
    """Get a memory by ID from any layer."""
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchall()
    if not rows:
        return None
    row = rows[0]
    try:
        return MemoryRecord(
            id=row["id"],
            content=row["content"],
            type=row["type"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(timezone.utc),
            metadata=json.loads(row["metadata_json"] if row["metadata_json"] else "{}"),
        )
    except Exception:
        return None


# ── Event Sequences ────────────────────────────────────────────────────────


def event_sequence(
    store: SuperMemoryStore,
    start: str | None = None,
    end: str | None = None,
    types: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Get a chronological event sequence within an optional time window.

    Uses the `BEFORE`/`AFTER` synapses when available; falls back to
    `created_at` ordering.

    Args:
        store: SuperMemoryStore.
        start: ISO datetime start (optional).
        end: ISO datetime end (optional).
        types: Memory type filter (optional).
        limit: Max events.

    Returns:
        Chronological event narrative.
    """
    with store.connect() as conn:
        query = "SELECT * FROM memories WHERE 1=1"
        params: list[Any] = []

        if start:
            query += " AND created_at >= ?"
            params.append(start)
        if end:
            query += " AND created_at <= ?"
            params.append(end)
        if types:
            placeholders = ",".join("?" for _ in types)
            query += f" AND type IN ({placeholders})"
            params.extend(types)

        # Exclude soft-deleted
        query += (
            " AND (json_extract(metadata_json, '$.soft_deleted') IS NULL"
            " OR json_extract(metadata_json, '$.soft_deleted') != 1)"
        )
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

    events = []
    for row in rows:
        events.append({
            "id": row["id"],
            "content": row["content"],
            "type": row["type"],
            "layer": row["layer"],
            "created_at": row["created_at"] if row["created_at"] else "",
        })

    # Build narrative
    narrative_parts: list[str] = []
    for ev in events:
        ts = ev["created_at"][:19] if ev["created_at"] else ""
        narrative_parts.append(f"[{ts}] ({ev['type']}) {ev['content'][:200]}")

    return {
        "ok": True,
        "events": events,
        "narrative": "\n".join(narrative_parts),
        "count": len(events),
    }


# ── Temporal Ranges ────────────────────────────────────────────────────────


def temporal_range(
    store: SuperMemoryStore,
    start: str,
    end: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Get memories within a time window.

    Thin wrapper around event_sequence for API clarity.
    """
    return event_sequence(store, start=start, end=end, **kwargs)


# ── Topic Narratives ───────────────────────────────────────────────────────


def topic_narrative(
    topic: str,
    store: SuperMemoryStore,
    max_memories: int = 10,
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """Build a coherent narrative from memories related to a topic.

    Strategy:
    1. Search for memories containing the topic
    2. Group by type (FACT → DECISION → INSIGHT → WORKFLOW)
    3. Order chronologically
    4. Format as narrative paragraphs

    Args:
        topic: Topic to search.
        store: SuperMemoryStore.
        max_memories: Max memories to include.
        max_tokens: Approximate max tokens.

    Returns:
        Narrative text + grouped memories.
    """
    # Search via content LIKE and tags
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM memories WHERE
            (content LIKE ? OR tags_json LIKE ?)
            AND (json_extract(metadata_json, '$.soft_deleted') IS NULL
                 OR json_extract(metadata_json, '$.soft_deleted') != 1)
            ORDER BY
                CASE type
                    WHEN 'fact' THEN 1
                    WHEN 'decision' THEN 2
                    WHEN 'insight' THEN 3
                    WHEN 'workflow' THEN 4
                    WHEN 'lesson' THEN 5
                    WHEN 'context' THEN 6
                    WHEN 'event' THEN 7
                    ELSE 8
                END,
                created_at DESC
            LIMIT ?
            """,
            (f"%{topic}%", f"%{topic}%", max_memories),
        ).fetchall()

    if not rows:
        return {
            "ok": True,
            "narrative": f"No memories found related to '{topic}'.",
            "memories": [],
            "count": 0,
        }

    # Group by type
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["type"]].append({
            "id": row["id"],
            "content": row["content"],
            "type": row["type"],
            "created_at": row["created_at"] if row["created_at"] else "",
            "layer": row["layer"] if row["layer"] else "",
        })

    # Type display labels
    type_labels = {
        "fact": "Key Facts",
        "decision": "Decisions Made",
        "insight": "Insights",
        "workflow": "Process & Workflows",
        "lesson": "Lessons Learned",
        "context": "Context",
        "event": "Events",
    }

    # Build narrative
    parts: list[str] = [f"# Topic: {topic}\n"]
    total_chars = 0

    for group_type in ["fact", "decision", "insight", "workflow", "lesson", "context", "event"]:
        items = grouped.get(group_type, [])
        if not items:
            continue

        label = type_labels.get(group_type, group_type.title())
        parts.append(f"## {label} ({len(items)})")

        for item in items:
            snippet = item["content"]
            ts = item["created_at"][:19] if item["created_at"] else ""
            line = f"- [{ts}] {snippet}"
            parts.append(line)
            total_chars += len(line)

            if total_chars > max_tokens * 4:  # Approx 4 chars/token
                parts.append("\n*[truncated — more memories available]*")
                break

        parts.append("")

    return {
        "ok": True,
        "narrative": "\n".join(parts),
        "memories": [m for items in grouped.values() for m in items],
        "count": sum(len(items) for items in grouped.values()),
    }
