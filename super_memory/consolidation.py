from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .graph import project_memory
from .models import MemoryRecord, MemoryScope, MemoryType
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jaccard_similarity(a: str, b: str) -> float:
    """Jaccard similarity for dedup detection."""
    tokens_a = set(re.split(r"\W+", a.lower()))
    tokens_b = set(re.split(r"\W+", b.lower()))
    tokens_a.discard("")
    tokens_b.discard("")
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def _detect_duplicates(memories: list[MemoryRecord], threshold: float = 0.85) -> list[dict[str, Any]]:
    """Find near-duplicate memories using Jaccard similarity."""
    clusters: list[dict[str, Any]] = []
    seen: set[str] = set()

    for i, mem_a in enumerate(memories):
        if mem_a.id in seen:
            continue
        group = [mem_a.id]
        for mem_b in memories[i + 1 :]:
            if mem_b.id in seen:
                continue
            sim = _jaccard_similarity(mem_a.content, mem_b.content)
            if sim >= threshold:
                group.append(mem_b.id)
                seen.add(mem_b.id)
        if len(group) > 1:
            clusters.append({
                "canonical": mem_a.id,
                "duplicates": group[1:],
                "content_preview": mem_a.content[:200],
                "count": len(group),
            })
            seen.add(mem_a.id)

    return clusters


def _detect_contradictions(memories: list[MemoryRecord]) -> list[dict[str, Any]]:
    """Detect contradicting decisions/preferences."""
    contradictions: list[dict[str, Any]] = []
    decisions = [m for m in memories if m.type in {MemoryType.DECISION, MemoryType.PREFERENCE}]

    # Simple keyword-based contradiction detection
    negation_words = {"not", "don't", "never", "avoid", "reject", "no"}

    for i, mem_a in enumerate(decisions):
        tokens_a = set(re.split(r"\W+", mem_a.content.lower()))
        has_negation_a = bool(tokens_a & negation_words)

        for mem_b in decisions[i + 1 :]:
            tokens_b = set(re.split(r"\W+", mem_b.content.lower()))
            has_negation_b = bool(tokens_b & negation_words)

            # Same topic but opposite negation
            overlap = tokens_a & tokens_b
            overlap.discard("")
            if len(overlap) >= 3 and has_negation_a != has_negation_b:
                contradictions.append({
                    "memory_a": mem_a.id,
                    "memory_b": mem_b.id,
                    "content_a": mem_a.content[:150],
                    "content_b": mem_b.content[:150],
                    "reason": "opposite_negation",
                })

    return contradictions


def _promotion_candidates(memories: list[MemoryRecord]) -> list[dict[str, Any]]:
    """Find memories that should be promoted to semantic/long-term."""
    candidates: list[dict[str, Any]] = []

    # Frequency-based promotion: repeated topics
    topic_counts: dict[str, list[str]] = defaultdict(list)
    for mem in memories:
        # Extract key nouns/entities as topics
        words = [w for w in re.split(r"\W+", mem.content.lower()) if len(w) > 4]
        for word in words[:5]:  # top 5 words as topics
            topic_counts[word].append(mem.id)

    for topic, mem_ids in topic_counts.items():
        if len(set(mem_ids)) >= 3:  # repeated 3+ times
            candidates.append({
                "topic": topic,
                "frequency": len(set(mem_ids)),
                "memory_ids": list(set(mem_ids))[:5],
                "reason": "frequent_topic",
            })

    # Type-based promotion: durable types
    for mem in memories:
        if mem.type in {MemoryType.DECISION, MemoryType.WORKFLOW, MemoryType.LESSON, MemoryType.DOCTRINE}:
            candidates.append({
                "memory_id": mem.id,
                "type": mem.type.value,
                "content": mem.content[:200],
                "reason": "durable_type",
            })

    return candidates


def _merge_duplicates(store: SuperMemoryStore, clusters: list[dict[str, Any]], dry_run: bool) -> list[dict[str, Any]]:
    """Merge duplicate memories: keep canonical, soft-delete duplicates, cite sources."""
    merged: list[dict[str, Any]] = []

    for cluster in clusters:
        canonical_id = cluster["canonical"]
        duplicate_ids = cluster["duplicates"]

        if dry_run:
            merged.append({
                "canonical": canonical_id,
                "merged_count": len(duplicate_ids),
                "action": "would_merge",
            })
            continue

        # Update canonical with citation metadata
        canonical = store.get_memory(canonical_id)
        if canonical:
            metadata = canonical.metadata.copy()
            metadata.setdefault("merged_from", []).extend(duplicate_ids)
            with store.connect() as conn:
                conn.execute(
                    "UPDATE memories SET metadata_json = ? WHERE id = ?",
                    (json.dumps(metadata, ensure_ascii=False), canonical_id),
                )

        # Soft-delete duplicates
        with store.connect() as conn:
            for dup_id in duplicate_ids:
                conn.execute(
                    "UPDATE memories SET metadata_json = json_set(metadata_json, '$.soft_deleted', 1) WHERE id = ?",
                    (dup_id,),
                )

        merged.append({
            "canonical": canonical_id,
            "merged_count": len(duplicate_ids),
            "action": "merged",
        })

    return merged


def _create_semantic_memories(store: SuperMemoryStore, config_path: str | None, candidates: list[dict[str, Any]], dry_run: bool) -> list[dict[str, Any]]:
    """Create semantic/summary memories from frequent patterns."""
    created: list[dict[str, Any]] = []

    for candidate in candidates:
        if candidate.get("reason") != "frequent_topic":
            continue
        if candidate["frequency"] < 3:
            continue

        topic = candidate["topic"]
        semantic_content = f"Semantic memory: '{topic}' appears frequently across {candidate['frequency']} memories."

        if dry_run:
            created.append({"topic": topic, "action": "would_create", "content": semantic_content})
            continue

        # Create semantic memory
        cfg = load_config(config_path)
        svc = SuperMemoryService(cfg)
        semantic_rec = MemoryRecord(
            content=semantic_content,
            type=MemoryType.CONTEXT,
            scope=MemoryScope.SHARED,
            agent_id="consolidation",
            project="super-memory",
            tags=["semantic", "consolidated", f"topic:{topic}"],
            source="consolidation.semantic_promotion",
            trust_score=0.75,
            metadata={"source_memory_ids": candidate["memory_ids"], "consolidation_topic": topic},
        )
        results = svc.save(semantic_rec)
        if results:
            created.append({"topic": topic, "action": "created", "memory_id": semantic_rec.id})

    return created


def consolidate_real(strategy: str = "all", dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    """
    Real consolidation pipeline:
    1. Detect duplicates (Jaccard > 0.85)
    2. Merge duplicates (keep canonical, cite sources)
    3. Detect contradictions
    4. Promote frequent patterns to semantic memories
    5. Rebuild graph projection
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)

    # Load memories
    rows = store.list_memory_rows(limit=500)
    memories = [row_to_memory(row) for row in rows]

    # Phase 1: Detect duplicates
    duplicate_clusters = _detect_duplicates(memories, threshold=0.85) if strategy in {"all", "dedup"} else []

    # Phase 2: Merge duplicates
    merged = _merge_duplicates(store, duplicate_clusters, dry_run) if duplicate_clusters else []

    # Phase 3: Detect contradictions
    contradictions = _detect_contradictions(memories) if strategy in {"all", "conflicts"} else []

    # Phase 4: Promotion candidates
    promotion = _promotion_candidates(memories) if strategy in {"all", "promote"} else []

    # Phase 5: Create semantic memories
    semantic_created = _create_semantic_memories(store, config_path, promotion, dry_run) if promotion else []

    # Phase 6: Rebuild graph projection.
    # - For merge/dedup consolidation, rebuild canonical merged memories.
    # - For explicit graph/all strategies, project all loaded memories so the
    #   maintenance endpoint is useful even when no duplicate merges occurred.
    graph_rebuilt = 0
    graph_errors: list[dict[str, str]] = []
    graph_targets: list[MemoryRecord] = []
    if strategy in {"all", "graph"}:
        graph_targets = memories
    elif merged:
        for merge_action in merged:
            if merge_action["action"] == "merged":
                canonical = store.get_memory(merge_action["canonical"])
                if canonical:
                    graph_targets.append(canonical)
    if not dry_run and graph_targets:
        for memory in graph_targets:
            try:
                project_memory(memory, config_path=config_path)
                graph_rebuilt += 1
            except Exception as exc:
                graph_errors.append({"memory_id": memory.id, "error": f"{type(exc).__name__}: {exc}"})

    return {
        "ok": True,
        "strategy": strategy,
        "dry_run": dry_run,
        "checked_memories": len(memories),
        "duplicate_clusters": len(duplicate_clusters),
        "merged": merged,
        "contradictions": contradictions[:10],
        "promotion_candidates": len(promotion),
        "semantic_created": semantic_created,
        "graph_rebuilt": graph_rebuilt,
        "graph_errors": graph_errors[:10],
        "real_consolidation": True,
    }
