"""Legacy Dream Engine facade backed by unified proposal governance.

All synthetic insights and weak-tie changes are proposals. Dry-run is read-only;
non-dry runs may enqueue deterministic pending proposals but never write
canonical memories or mutate synapse weights.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .dream_governance import (
    MAX_PROPOSALS_PER_RUN,
    build_proposal,
    canonical_content_exists,
    deterministic_run_key,
    enqueue_proposal,
    readonly_connection,
)
from .storage import SuperMemoryStore, row_to_memory

_DREAM_DRY_RUN_LIMIT = 200
_MAX_SCAN = 500
_SOURCE_FILTER = """
 AND COALESCE(agent_id, '') NOT IN ('dream-engine', 'self-improvement-engine')
 AND lower(COALESCE(source, '')) NOT LIKE 'super-memory.dream%'
 AND lower(COALESCE(source, '')) NOT LIKE 'self-improvement%'
 AND COALESCE(json_extract(metadata_json, '$.generated_by'), '') = ''
 AND COALESCE(json_extract(metadata_json, '$.governance_proposal_id'), '') = ''
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_limit(value: int) -> int:
    return max(1, min(int(value), _MAX_SCAN))


def _store(config_path: str | None = None) -> SuperMemoryStore:
    """Return a store without creating dream schemas (important for dry-run)."""
    return SuperMemoryStore(load_config(config_path))


def _init_tables(store: SuperMemoryStore) -> None:
    """Legacy table initializer retained for compatibility, never used by runs."""
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dream_events (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                pattern_type TEXT NOT NULL,
                strength REAL NOT NULL DEFAULT 0.5,
                source_text TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                reviewed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dream_events_kind ON dream_events(kind)")


def _remember_internal(
    content: str,
    mem_type: str,
    tags: list[str],
    config_path: str | None = None,
) -> dict[str, Any]:
    """Compatibility helper: enqueue a proposal instead of saving a memory."""
    store = _store(config_path)
    proposal = build_proposal(
        kind="dream_insight",
        content=content,
        evidence={"tags": tags, "legacy_memory_type": mem_type},
        action={"type": "create_memory", "memory_type": "insight", "scope": "project"},
    )
    if canonical_content_exists(store, proposal["content_hash"]):
        return {"ok": False, "skipped": "duplicate_canonical", "proposal": proposal}
    result = enqueue_proposal(store, proposal, dry_run=False)
    return {
        "ok": True,
        "pending_approval": True,
        "proposal": result["proposal"],
        "deduplicated": result["deduplicated"],
    }


def _extract_keywords(text: str, top_n: int = 8) -> list[str]:
    """Deterministic bounded keyword extraction."""
    stop = {
        "the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "on",
        "is", "are", "was", "were", "be", "by", "as", "this", "that", "it",
        "at", "from", "but", "not", "we", "they", "has", "have", "had", "do",
        "does", "did", "will", "would", "can", "could", "should", "may", "might",
    }
    tokens = [token.lower() for token in re.split(r"\W+", (text or "")[:20_000]) if len(token) > 3 and token.lower() not in stop]
    return [token for token, _ in Counter(tokens).most_common(max(1, min(int(top_n), 20)))]


def _jaccard_similarity(a: str, b: str) -> float:
    tokens_a = {token for token in re.split(r"\W+", (a or "").lower()) if token}
    tokens_b = {token for token in re.split(r"\W+", (b or "").lower()) if token}
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


_DREAM_NOISE_TOKENS = {
    "license", "licence", "copyright", "software", "memory", "python", "code",
    "file", "files", "content", "data", "system", "protocol", "chunked",
    "write", "operation", "operations", "line", "lines", "maximum", "mandatory",
    "note", "notes", "text", "value", "result", "error", "config", "table",
    "user", "assistant", "message", "task",
}
_DREAM_INJECTION_MARKERS = (
    "chunked write protocol", "maximum 350 lines", "no exceptions",
    "server timeout", "mandatory", "absolute limits", "per single write",
)


def _is_dream_noise(text: str, keywords: list[str] | set[str] | None = None) -> bool:
    """Reject ambient-token patterns and known instruction-injection echoes."""
    lowered = (text or "").lower()
    if any(marker in lowered for marker in _DREAM_INJECTION_MARKERS):
        return True
    clean_keywords = {keyword.lower() for keyword in (keywords or []) if keyword}
    return bool(clean_keywords and clean_keywords <= _DREAM_NOISE_TOKENS)


def _quality_score(content: str) -> float:
    try:
        from .quality_scorer import score_memory

        return float(score_memory(content, memory_type="insight").overall)
    except Exception:
        return 0.0


def dream_insight_generation(limit: int = 200, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    """Generate bounded bridge-insight proposals from non-generated memories."""
    bounded_limit = _bounded_limit(limit)
    store = _store(config_path)
    with readonly_connection(store) as conn:
        if conn is None:
            rows = []
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0"
                + _SOURCE_FILTER
                + " ORDER BY created_at DESC, id LIMIT ?",
                (bounded_limit,),
            ).fetchall()

    # Collapse layer replicas before candidate generation.
    records: dict[str, dict[str, Any]] = {}
    for row in rows:
        rec = row_to_memory(row)
        if rec.id in records:
            continue
        keywords = tuple(_extract_keywords(rec.content, top_n=5))
        if keywords:
            records[rec.id] = {
                "id": rec.id,
                "content": rec.content[:4_000],
                "type": rec.type.value,
                "keywords": keywords,
            }

    items = [records[key] for key in sorted(records)]
    candidates: list[dict[str, Any]] = []
    for index, first in enumerate(items):
        for second in items[index + 1 :]:
            similarity = _jaccard_similarity(first["content"], second["content"])
            if not 0.15 < similarity < 0.75:
                continue
            shared = sorted(set(first["keywords"]) & set(second["keywords"]))
            if not shared or _is_dream_noise(first["content"] + " " + second["content"], shared):
                continue
            source_ids = sorted([first["id"], second["id"]])
            proposed = f"Bridge insight: {' and '.join(shared)} connects {first['type']}->{second['type']} knowledge"
            content = (
                f"Dream insight: '{proposed}' (similarity={similarity:.3f}, "
                f"from memories {source_ids[0][:12]} and {source_ids[1][:12]})"
            )[:4_000]
            candidates.append(
                {
                    "source_a": {"id": first["id"], "content": first["content"][:160], "type": first["type"]},
                    "source_b": {"id": second["id"], "content": second["content"][:160], "type": second["type"]},
                    "cross_similarity": round(similarity, 3),
                    "shared_keywords": shared[:10],
                    "proposed_insight": proposed,
                    "content": content,
                    "source_ids": source_ids,
                }
            )
    candidates.sort(key=lambda item: (-item["cross_similarity"], item["source_ids"]))
    candidates = candidates[: min(10, MAX_PROPOSALS_PER_RUN)]
    run_key = deterministic_run_key(
        "dream-legacy-insights-v2",
        inputs={"limit": bounded_limit},
        source_ids=[source_id for candidate in candidates for source_id in candidate["source_ids"]],
    )

    proposals: list[dict[str, Any]] = []
    queued = deduplicated = skipped_quality = skipped_canonical = 0
    for candidate in candidates:
        quality = _quality_score(candidate["content"])
        if quality < 0.5:
            skipped_quality += 1
            continue
        proposal = build_proposal(
            kind="dream_insight",
            content=candidate["content"],
            source_ids=candidate["source_ids"],
            run_key=run_key,
            evidence={
                "cross_similarity": candidate["cross_similarity"],
                "shared_keywords": candidate["shared_keywords"],
                "quality_overall": round(quality, 4),
            },
            action={"type": "create_memory", "memory_type": "insight", "scope": "project"},
        )
        if canonical_content_exists(store, proposal["content_hash"]):
            skipped_canonical += 1
            continue
        outcome = enqueue_proposal(store, proposal, dry_run=dry_run)
        queued += int(bool(outcome["created"]))
        deduplicated += int(bool(outcome["deduplicated"]))
        proposals.append(outcome["proposal"])

    return {
        "ok": True,
        "dry_run": dry_run,
        "run_key": run_key,
        "governance_state": "preview" if dry_run else "pending_approval",
        "clusters_found": len(records),
        "candidate_bridges": len(candidates),
        "insights_generated": len(proposals),
        "memories_created": 0,
        "proposals_queued": queued,
        "deduplicated": deduplicated,
        "skipped_low_quality": skipped_quality,
        "skipped_canonical_duplicate": skipped_canonical,
        "insights": candidates[:10],
        "proposals": proposals,
    }


def dream_weak_tie_reinforcement(limit: int = 200, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    """Propose weak-tie reinforcement; never update synapses directly."""
    bounded_limit = _bounded_limit(limit)
    store = _store(config_path)
    with readonly_connection(store) as conn:
        try:
            if conn is None:
                raise LookupError("database does not exist")
            weak_synapses = conn.execute(
                "SELECT * FROM cognitive_synapses WHERE weight < 0.3 AND weight > 0.05 ORDER BY weight ASC, id LIMIT ?",
                (min(bounded_limit // 2, MAX_PROPOSALS_PER_RUN),),
            ).fetchall()
        except Exception:
            weak_synapses = []

    source_ids = [str(synapse["id"]) for synapse in weak_synapses]
    run_key = deterministic_run_key(
        "dream-weak-ties-v2",
        inputs={"limit": bounded_limit, "multiplier": 1.5},
        source_ids=source_ids,
    )
    proposals: list[dict[str, Any]] = []
    queued = deduplicated = 0
    for synapse in weak_synapses:
        old_weight = float(synapse["weight"])
        new_weight = min(1.0, old_weight * 1.5)
        proposal = build_proposal(
            kind="dream_weak_tie",
            content=f"Propose reinforcing synapse {synapse['id']} from {old_weight:.6f} to {new_weight:.6f}",
            source_ids=[synapse["id"]],
            run_key=run_key,
            evidence={"old_weight": old_weight, "new_weight": new_weight},
            action={"type": "update_synapse_weight", "synapse_id": synapse["id"], "new_weight": new_weight},
        )
        outcome = enqueue_proposal(store, proposal, dry_run=dry_run)
        queued += int(bool(outcome["created"]))
        deduplicated += int(bool(outcome["deduplicated"]))
        proposals.append(outcome["proposal"])

    return {
        "ok": True,
        "dry_run": dry_run,
        "run_key": run_key,
        "governance_state": "preview" if dry_run else "pending_approval",
        "weak_synapses_found": len(weak_synapses),
        "reinforced": [],
        "proposals": proposals,
        "proposals_queued": queued,
        "deduplicated": deduplicated,
        "method": "weak_tie_boost_1.5x_proposal_only",
    }


def dream_pattern_summary(limit: int = 200, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    """Report token-frequency patterns; statistics are never persisted."""
    bounded_limit = _bounded_limit(limit)
    store = _store(config_path)
    with readonly_connection(store) as conn:
        if conn is None:
            rows = []
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0"
                + _SOURCE_FILTER
                + " ORDER BY created_at DESC, id LIMIT ?",
                (bounded_limit,),
            ).fetchall()

    keyword_counts: Counter[str] = Counter()
    memory_ids_by_keyword: defaultdict[str, set[str]] = defaultdict(set)
    seen_memories: set[str] = set()
    for row in rows:
        rec = row_to_memory(row)
        if rec.id in seen_memories:
            continue
        seen_memories.add(rec.id)
        for keyword in set(_extract_keywords(rec.content, top_n=6)):
            keyword_counts[keyword] += 1
            memory_ids_by_keyword[keyword].add(rec.id)

    patterns = [
        {
            "keyword": keyword,
            "frequency": count,
            "unique_memories": len(memory_ids_by_keyword[keyword]),
            "sources": sorted(memory_ids_by_keyword[keyword])[:5],
        }
        for keyword, count in keyword_counts.most_common(50)
        if keyword.lower() not in _DREAM_NOISE_TOKENS and count >= 4 and len(memory_ids_by_keyword[keyword]) >= 3
    ]
    return {
        "ok": True,
        "dry_run": dry_run,
        "unique_keywords_found": len(keyword_counts),
        "patterns_detected": len(patterns),
        "patterns": patterns[:15],
        "memories_created": 0,
        "note": "token-frequency patterns are reported only, not persisted",
    }


def dream_full_cycle(limit: int = 200, dry_run: bool = True, config_path: str | None = None) -> dict[str, Any]:
    """Run all governed legacy phases with deterministic proposal-only output."""
    phase1 = dream_insight_generation(limit=limit, dry_run=dry_run, config_path=config_path)
    phase2 = dream_weak_tie_reinforcement(limit=limit, dry_run=dry_run, config_path=config_path)
    phase3 = dream_pattern_summary(limit=limit, dry_run=dry_run, config_path=config_path)
    run_key = deterministic_run_key(
        "dream-full-cycle-v2",
        inputs={"limit": _bounded_limit(limit)},
        source_ids=[phase1["run_key"], phase2["run_key"]],
    )
    return {
        "ok": True,
        "dry_run": dry_run,
        "mode": "full_dream_cycle",
        "run_key": run_key,
        "governance": {"review_required": True, "direct_mutation_disabled": True},
        "phase1_insights": {
            "bridges_found": phase1["candidate_bridges"],
            "created": 0,
            "proposals_queued": phase1["proposals_queued"],
        },
        "phase2_reinforcement": {
            "weak_synapses_found": phase2["weak_synapses_found"],
            "reinforced": 0,
            "proposals_queued": phase2["proposals_queued"],
        },
        "phase3_patterns": {"patterns_detected": phase3["patterns_detected"], "created": 0},
        "total_memories_created": 0,
        "total_proposals_queued": phase1["proposals_queued"] + phase2["proposals_queued"],
    }
