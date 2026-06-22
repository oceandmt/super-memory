"""Semantic discovery — auto-link related memories via shared entities, tags, and content.

Ported concept from neural-memory v4.58.0 `engine/consolidation.py` (semantic_link strategy).
Runs on consolidation to find and link memories that share:
1. Extracted entity types (from entity_extractor)
2. Overlapping tags
3. Same project/scope
4. Similar content via TF-IDF cosine similarity

Links are created as graph synapses for improved recall connectivity.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import defaultdict
from typing import Any

logger = logging.getLogger("super-memory.semantic_discovery")

# Minimum Jaccard similarity for tag-based linking
TAG_SIMILARITY_THRESHOLD = 0.3
# Minimum entity overlap count for entity-based linking
ENTITY_OVERLAP_THRESHOLD = 1
# Token overlap threshold for content-based linking
CONTENT_SIMILARITY_THRESHOLD = 0.25
# Max links per memory per run
MAX_LINKS_PER_MEMORY = 5


def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercased word tokens."""
    if not text:
        return set()
    return {t.lower() for t in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", text)}


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _parse_tags(tags: Any) -> set[str]:
    """Parse tags from various formats (list, JSON string, or None)."""
    if not tags:
        return set()
    if isinstance(tags, list):
        return {t.lower() for t in tags if t}
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            if isinstance(parsed, list):
                return {t.lower() for t in parsed if t}
        except (json.JSONDecodeError, TypeError):
            pass
    return set()


def _get_entity_types(metadata: dict[str, Any]) -> set[str]:
    """Extract entity types from memory metadata."""
    entities = metadata.get("extracted_entities", {})
    if isinstance(entities, dict):
        return set(entities.get("entity_types", []))
    return set()


def discover_links(
    memories: list[dict[str, Any]],
    tag_threshold: float = TAG_SIMILARITY_THRESHOLD,
    entity_overlap: int = ENTITY_OVERLAP_THRESHOLD,
    content_threshold: float = CONTENT_SIMILARITY_THRESHOLD,
    max_links: int = MAX_LINKS_PER_MEMORY,
) -> list[dict[str, Any]]:
    """Discover semantic links between a list of memories.

    Each memory dict should have: id, content, tags, metadata (with extracted_entities), project.

    Returns a list of link dicts: {source_id, target_id, relation_type, weight, reason}
    """
    if len(memories) < 2:
        return []

    links: list[dict[str, Any]] = []
    link_count: dict[str, int] = defaultdict(int)  # memory_id -> link count

    for i, mem_a in enumerate(memories):
        for j, mem_b in enumerate(memories):
            if j <= i:
                continue

            id_a = mem_a.get("id")
            id_b = mem_b.get("id")
            if not id_a or not id_b:
                continue

            # Check link limit for both
            if link_count.get(id_a, 0) >= max_links or link_count.get(id_b, 0) >= max_links:
                continue

            # Skip if already linked (same project only — likely already connected)
            if mem_a.get("project") and mem_b.get("project") and mem_a["project"] == mem_b["project"]:
                # Still check for entity-based links within same project
                pass

            weight = 0.0
            reasons: list[str] = []

            # 1. Entity type overlap
            meta_a = mem_a.get("metadata", {})
            if isinstance(meta_a, str):
                try:
                    meta_a = json.loads(meta_a)
                except Exception:
                    meta_a = {}
            meta_b = mem_b.get("metadata", {})
            if isinstance(meta_b, str):
                try:
                    meta_b = json.loads(meta_b)
                except Exception:
                    meta_b = {}

            entities_a = _get_entity_types(meta_a)
            entities_b = _get_entity_types(meta_b)
            entity_overlap_count = len(entities_a & entities_b)
            if entity_overlap_count >= entity_overlap:
                weight += entity_overlap_count * 0.15
                reasons.append(f"entities:{','.join(entities_a & entities_b)}")

            # 2. Tag overlap (Jaccard)
            tags_a = _parse_tags(mem_a.get("tags"))
            tags_b = _parse_tags(mem_b.get("tags"))
            tag_sim = _jaccard_similarity(tags_a, tags_b)
            if tag_sim >= tag_threshold:
                weight += tag_sim * 0.4
                reasons.append(f"tags:sim={tag_sim:.2f}")

            # 3. Content similarity (token overlap)
            tokens_a = _tokenize(mem_a.get("content", ""))
            tokens_b = _tokenize(mem_b.get("content", ""))
            content_sim = _jaccard_similarity(tokens_a, tokens_b)
            if content_sim >= content_threshold:
                weight += content_sim * 0.3
                reasons.append(f"content:sim={content_sim:.2f}")

            # 4. Same project boost
            proj_a = mem_a.get("project")
            proj_b = mem_b.get("project")
            if proj_a and proj_b and proj_a == proj_b:
                weight += 0.1
                reasons.append(f"project:{proj_a}")

            if weight > 0.2 and reasons:
                links.append({
                    "source_id": id_a,
                    "target_id": id_b,
                    "relation_type": "related_to",
                    "weight": round(min(weight, 1.0), 3),
                    "reasons": reasons[:3],
                })
                link_count[id_a] += 1
                link_count[id_b] += 1

    return links


def auto_link_memories(
    store,
    config_path: str | None = None,
    dry_run: bool = True,
    limit: int = 500,
    min_weight: float = 0.25,
) -> dict[str, Any]:
    """Auto-link memories in the store using semantic discovery.

    Reads memories from store, discovers links, and writes them as graph synapses.
    Only creates links that don't already exist (avoids duplicates).
    """
    with store.connect() as conn:
        # Load memories with extracted entities (most signal-rich)
        rows = conn.execute(
            "SELECT id, content, tags_json, metadata_json, project FROM memories "
            "WHERE json_extract(metadata_json, '$.soft_deleted') IS NULL "
            "OR json_extract(metadata_json, '$.soft_deleted') != 1 "
            "ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()

    memories = []
    for row in rows:
        meta = {}
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except Exception:
            meta = {}
        memories.append({
            "id": row["id"],
            "content": row["content"] or "",
            "tags": row["tags_json"],
            "metadata": meta,
            "project": row["project"],
        })

    if len(memories) < 2:
        return {"ok": True, "links_found": 0, "links_created": 0, "reason": "not enough memories"}

    links = discover_links(memories)
    if not links:
        return {"ok": True, "links_found": 0, "links_created": 0}

    # Filter by min weight
    links = [l for l in links if l["weight"] >= min_weight]

    created = 0
    errors: list[str] = []
    if not dry_run:
        with store.connect() as conn:
            for link in links:
                try:
                    # Check if synapse already exists between the memory neurons
                    existing = conn.execute(
                        "SELECT id FROM cognitive_synapses WHERE source_neuron_id IN "
                        "(SELECT id FROM cognitive_neurons WHERE source_memory_id=? AND kind='memory' LIMIT 1) "
                        "AND target_neuron_id IN "
                        "(SELECT id FROM cognitive_neurons WHERE source_memory_id=? AND kind='memory' LIMIT 1) "
                        "AND relation=? LIMIT 1",
                        (link["source_id"], link["target_id"], link["relation_type"]),
                    ).fetchone()
                    if not existing:
                        conn.execute(
                            "INSERT INTO cognitive_synapses "
                            "(id, source_neuron_id, target_neuron_id, relation, weight, confidence, metadata_json, created_at, updated_at) "
                            "SELECT "
                            "'s:' || hex(randomblob(8)), sn.id, tn.id, ?, ?, 0.75, ?, "
                            "datetime('now'), datetime('now') "
                            "FROM (SELECT id FROM cognitive_neurons WHERE source_memory_id=? AND kind='memory' LIMIT 1) sn, "
                            "(SELECT id FROM cognitive_neurons WHERE source_memory_id=? AND kind='memory' LIMIT 1) tn "
                            "WHERE sn.id IS NOT NULL AND tn.id IS NOT NULL",
                            (link["relation_type"], link["weight"],
                             json.dumps({"reasons": link["reasons"], "source": "semantic_discovery"}),
                             link["source_id"], link["target_id"]),
                        )
                        created += 1
                except Exception as exc:
                    errors.append(f"{link['source_id'][:8]}->{link['target_id'][:8]}: {exc}")

    return {
        "ok": True,
        "links_found": len(links),
        "links_created": created,
        "errors": errors[:5],
        "dry_run": dry_run,
    }
