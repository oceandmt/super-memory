"""Governed dream consolidation engine.

Dream cycles are evidence readers and proposal generators. Generated insights
never become canonical memories until an explicit approval call succeeds.
Dry-run mode is read-only: it does not create schemas, queue rows, artifacts,
or memories.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import load_config
from .dream_governance import (
    MAX_PROPOSALS_PER_RUN,
    build_proposal,
    canonical_content_exists,
    deterministic_run_key,
    enqueue_proposal,
    ensure_schema,
    get_proposal,
    list_proposals,
    readonly_connection,
    resolve_proposal,
)
from .models import MemoryRecord, MemoryScope, MemoryType
from .storage import SuperMemoryStore

_MAX_SCAN = 500
_GENERATED_FILTER = """
 AND COALESCE(agent_id, '') NOT IN ('dream-engine', 'self-improvement-engine')
 AND lower(COALESCE(source, '')) NOT LIKE 'super-memory.dream%'
 AND lower(COALESCE(source, '')) NOT LIKE 'self-improvement%'
 AND COALESCE(json_extract(metadata_json, '$.generated_by'), '') = ''
 AND COALESCE(json_extract(metadata_json, '$.governance_proposal_id'), '') = ''
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_limit(value: int, maximum: int = _MAX_SCAN) -> int:
    return max(1, min(int(value), maximum))


def _jaccard_similarity(a: str, b: str) -> float:
    tokens_a = {token for token in re.split(r"\W+", a.lower()) if token}
    tokens_b = {token for token in re.split(r"\W+", b.lower()) if token}
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _token_frequencies(store: SuperMemoryStore, limit: int = 1000) -> dict[str, float]:
    """Build inverse token frequency over bounded, human-origin memories."""
    with readonly_connection(store) as conn:
        if conn is None:
            return {}
        rows = conn.execute(
            "SELECT content FROM memories WHERE "
            "COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 "
            + _GENERATED_FILTER
            + " ORDER BY created_at DESC LIMIT ?",
            (_bounded_limit(limit),),
        ).fetchall()
    token_counts: Counter[str] = Counter()
    for row in rows:
        content = row["content"] if hasattr(row, "keys") else row[0]
        for token in {token for token in re.split(r"\W+", (content or "").lower()) if token}:
            token_counts[token] += 1
    total = len(rows)
    return {token: math.log(total / max(1, count)) for token, count in token_counts.items()} if total else {}


def _compute_surprisal(content: str, token_weights: dict[str, float]) -> float:
    tokens = [token for token in re.split(r"\W+", (content or "").lower()) if token]
    if not tokens:
        return 0.0
    unseen = max(token_weights.values(), default=0.0) + math.log(2.0)
    scores = [token_weights.get(token, unseen) for token in tokens]
    return sum(scores) / len(scores)


def rank_by_surprisal(
    store: SuperMemoryStore,
    limit: int = 200,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """Rank bounded source memories by novelty; this function is always read-only."""
    bounded_limit = _bounded_limit(limit)
    token_weights = _token_frequencies(store, limit=bounded_limit)
    with readonly_connection(store) as conn:
        if conn is None:
            return []
        rows = conn.execute(
            """SELECT id, content, type, agent_id, session_id, created_at
               FROM memories
               WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0"""
            + _GENERATED_FILTER
            + " ORDER BY created_at DESC LIMIT ?",
            (bounded_limit,),
        ).fetchall()
    scored = [
        {
            "id": row["id"],
            "content": (row["content"] or "")[:200],
            "type": row["type"],
            "agent_id": row["agent_id"],
            "session_id": row["session_id"],
            "surprisal": round(_compute_surprisal(row["content"] or "", token_weights), 3),
        }
        for row in rows
    ]
    scored.sort(key=lambda item: (-item["surprisal"], item["id"]))
    return scored


def detect_patterns(
    store: SuperMemoryStore,
    window_hours: int = 24,
    min_cluster_size: int = 2,
    similarity_threshold: float = 0.4,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """Detect bounded cross-session patterns without consuming generated output."""
    bounded_hours = max(1, min(int(window_hours), 24 * 365))
    bounded_cluster = max(2, min(int(min_cluster_size), 50))
    bounded_threshold = max(0.0, min(float(similarity_threshold), 1.0))
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=bounded_hours)).isoformat()
    with readonly_connection(store) as conn:
        if conn is None:
            return []
        rows = conn.execute(
            """SELECT id, content, type, agent_id, session_id, created_at
               FROM memories WHERE created_at > ?
               AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0"""
            + _GENERATED_FILTER
            + " ORDER BY created_at DESC, id LIMIT ?",
            (cutoff, _MAX_SCAN),
        ).fetchall()

    # Similarity is an undirected graph; connected components make clustering
    # transitive and independent of row/seed order.
    items = [dict(row) for row in rows]
    adjacency = {str(item["id"]): set() for item in items}
    pair_similarity: dict[tuple[str, str], float] = {}
    for index, first in enumerate(items):
        for second in items[index + 1:]:
            sim = _jaccard_similarity(first.get("content") or "", second.get("content") or "")
            pair_similarity[(str(first["id"]), str(second["id"]))] = sim
            if sim >= bounded_threshold:
                adjacency[str(first["id"])].add(str(second["id"])); adjacency[str(second["id"])].add(str(first["id"]))
    by_id = {str(item["id"]): item for item in items}
    clusters: list[dict[str, Any]] = []
    used: set[str] = set()
    token_weights = _token_frequencies(store, limit=_MAX_SCAN)
    for root in sorted(by_id):
        if root in used: continue
        stack=[root]; component=[]; used.add(root)
        while stack:
            node=stack.pop(); component.append(node)
            for neighbor in sorted(adjacency[node]):
                if neighbor not in used: used.add(neighbor); stack.append(neighbor)
        group=[by_id[node] for node in sorted(component)]
        if len(group) < bounded_cluster:
            continue
        sessions = {item["session_id"] for item in group if item.get("session_id")}
        memory_ids = sorted(str(item["id"]) for item in group)[:64]
        clusters.append(
            {
                "size": len(group),
                "sessions": len(sessions),
                "cross_session": len(sessions) > 1,
                "content_samples": [(item.get("content") or "")[:150] for item in group[:3]],
                "agent_ids": sorted({item["agent_id"] for item in group if item.get("agent_id")})[:20],
                "memory_ids": memory_ids,
                "avg_surprisal": round(sum(_compute_surprisal(item.get("content") or "", token_weights) for item in group) / len(group), 3),
                "avg_pairwise_similarity": round(sum(_jaccard_similarity(a.get("content") or "", b.get("content") or "") for i,a in enumerate(group) for b in group[i+1:]) / max(1, len(group)*(len(group)-1)/2), 3),
            }
        )
    clusters.sort(key=lambda item: (-item["size"], item["memory_ids"]))
    return clusters


def generate_insight(cluster: dict[str, Any]) -> str:
    """Generate a bounded extractive candidate from a cluster."""
    samples = [str(sample)[:150] for sample in cluster.get("content_samples", [])[:3] if sample]
    if not samples:
        return ""
    best = max(samples, key=lambda sample: (len(sample), sample))
    cross = "Cross-session" if cluster.get("cross_session") else "Single-session"
    return (
        f"[Dream Consolidation] {cross} pattern — {int(cluster.get('size', 0))} related memories "
        f"across {int(cluster.get('sessions', 0))} session(s). Representative observation (extractive): {best}"
    )[:4_000]


def _quality_score(content: str) -> float:
    try:
        from .quality_scorer import score_memory

        return float(score_memory(content, memory_type="insight").overall)
    except Exception:
        return 0.0


def _dream_proposal(cluster: dict[str, Any], content: str, *, run_key: str, quality: float) -> dict[str, Any]:
    return build_proposal(
        kind="dream_insight",
        content=content,
        source_ids=cluster.get("memory_ids", []),
        run_key=run_key,
        evidence={
            "cluster_size": cluster.get("size", 0),
            "cross_session": bool(cluster.get("cross_session")),
            "sessions": cluster.get("sessions", 0),
            "quality_overall": round(quality, 4),
        },
        action={"type": "create_memory", "memory_type": "insight", "scope": "project"},
    )


def run_dream_cycle(
    store: SuperMemoryStore,
    *,
    dry_run: bool = True,
    window_hours: int = 24,
    min_cluster_size: int = 2,
    similarity_threshold: float = 0.4,
    max_insights: int = 5,
    require_review: bool = False,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Run the governed dream cycle.

    ``require_review`` remains for call compatibility but direct-save behavior
    has been retired. Both values route candidates to pending governance; a
    separate explicit approval is the only canonical write path.
    """
    bounded_max = max(0, min(int(max_insights), MAX_PROPOSALS_PER_RUN))
    ranked = rank_by_surprisal(store, limit=200, dry_run=True)
    clusters = detect_patterns(
        store,
        window_hours=window_hours,
        min_cluster_size=min_cluster_size,
        similarity_threshold=similarity_threshold,
        dry_run=True,
    )
    source_ids = sorted({source_id for cluster in clusters[:bounded_max] for source_id in cluster["memory_ids"]})
    run_key = deterministic_run_key(
        "dream-cycle-v2",
        inputs={
            "window_hours": max(1, min(int(window_hours), 24 * 365)),
            "min_cluster_size": max(2, min(int(min_cluster_size), 50)),
            "similarity_threshold": max(0.0, min(float(similarity_threshold), 1.0)),
            "max_insights": bounded_max,
        },
        source_ids=source_ids,
    )

    candidates: list[dict[str, Any]] = []
    queued = 0
    deduplicated = 0
    skipped_quality = 0
    skipped_noise = 0
    skipped_canonical = 0
    for cluster in clusters[:bounded_max]:
        content = generate_insight(cluster)
        if not content:
            continue
        try:
            from .dream import _is_dream_noise

            if _is_dream_noise(content):
                skipped_noise += 1
                continue
        except Exception:
            pass
        quality = _quality_score(content)
        if quality < 0.5:
            skipped_quality += 1
            continue
        proposal = _dream_proposal(cluster, content, run_key=run_key, quality=quality)
        if canonical_content_exists(store, proposal["content_hash"]):
            skipped_canonical += 1
            continue
        outcome = enqueue_proposal(store, proposal, dry_run=dry_run)
        queued += int(bool(outcome.get("created")))
        deduplicated += int(bool(outcome.get("deduplicated")))
        candidates.append(outcome["proposal"])

    return {
        "ok": True,
        "dry_run": dry_run,
        "run_key": run_key,
        "governance": {
            "state": "preview" if dry_run else "pending_approval",
            "review_required": True,
            "legacy_require_review_argument": require_review,
            "direct_save_disabled": True,
        },
        "window_hours": max(1, min(int(window_hours), 24 * 365)),
        "phases": {
            "surprisal": {"memories_scored": len(ranked), "top_surprisal": ranked[:5]},
            "patterns": {"clusters_found": len(clusters), "clusters": clusters[:bounded_max]},
            "insights": {
                "candidates": candidates,
                "would_enqueue": len(candidates) if dry_run else 0,
                "queued": queued,
                "deduplicated": deduplicated,
                "quality_gate": {
                    "skipped_low_quality": skipped_quality,
                    "skipped_noise": skipped_noise,
                    "skipped_canonical_duplicate": skipped_canonical,
                },
                "saved": 0,
                "require_review": True,
            },
        },
        "insights_saved": 0,
    }


# Compatibility wrappers for the former dream_pending_insights API. The
# additive generated_proposals table is now the single source of lifecycle
# truth; no new rows are written to the legacy table.
def _init_pending_insights(store: SuperMemoryStore) -> None:
    ensure_schema(store)


def _enqueue_pending_insight(
    store: SuperMemoryStore,
    ins: dict[str, Any],
    *,
    quality_overall: float | None = None,
) -> str:
    source_ids = ins.get("source_memory_ids", [])
    proposal = build_proposal(
        kind="dream_insight",
        content=str(ins.get("content", "")),
        source_ids=source_ids,
        evidence={
            "cluster_size": int(ins.get("cluster_size", 0)),
            "cross_session": bool(ins.get("cross_session")),
            "quality_overall": quality_overall,
        },
        action={"type": "create_memory", "memory_type": "insight", "scope": "project"},
    )
    return enqueue_proposal(store, proposal, dry_run=False)["proposal"]["id"]


def dream_list_pending_insights(
    store: SuperMemoryStore | None = None,
    *,
    limit: int = 50,
    config_path: str | None = None,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    active_store = store or SuperMemoryStore(cfg)
    proposals = list_proposals(active_store, kind="dream_insight", status="pending", limit=limit)
    items = [
        {
            "id": proposal["id"],
            "content": proposal["content"],
            "cluster_size": int(proposal.get("evidence", {}).get("cluster_size", 0)),
            "cross_session": bool(proposal.get("evidence", {}).get("cross_session")),
            "source_memory_ids": proposal.get("source_ids", []),
            "quality_overall": proposal.get("evidence", {}).get("quality_overall"),
            "created_at": proposal.get("created_at"),
            "run_key": proposal.get("run_key"),
            "status": proposal.get("status"),
        }
        for proposal in proposals
    ]
    return {"ok": True, "pending": items, "count": len(items)}


def _save_approved_dream(proposal: dict[str, Any], cfg: Any, store: SuperMemoryStore) -> str:
    existing = canonical_content_exists(store, proposal["content_hash"])
    if existing:
        return existing
    memory_id = f"dream-insight:{proposal['content_hash'][:32]}"
    evidence = proposal.get("evidence", {})
    record = MemoryRecord(
        id=memory_id,
        content=proposal["content"],
        type=MemoryType.INSIGHT,
        scope=MemoryScope.PROJECT,
        agent_id="dream-engine",
        project="super-memory",
        source="super-memory.dream.approved",
        tags=["dream-consolidation", "insight", "reviewed"],
        metadata={
            "dream_cluster_size": evidence.get("cluster_size"),
            "dream_cross_session": bool(evidence.get("cross_session")),
            "dream_source_ids": proposal.get("source_ids", []),
            "dream_generated_at": _now(),
            "quality_overall": evidence.get("quality_overall"),
            "review_status": "approved",
            "generated_by": "dream_engine",
            "governance_proposal_id": proposal["id"],
            "governance_run_key": proposal["run_key"],
        },
    )
    from .service import SuperMemoryService

    results = SuperMemoryService(cfg).save(record)
    if not any(getattr(result, "ok", False) for result in results):
        raise RuntimeError("canonical save returned no successful layer")
    return memory_id


def dream_approve_insight(
    insight_id: str,
    store: SuperMemoryStore | None = None,
    *,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Explicitly approve one pending proposal and save it canonically once."""
    cfg = load_config(config_path)
    active_store = store or SuperMemoryStore(cfg)
    proposal = get_proposal(active_store, insight_id)
    if proposal and proposal.get("kind") != "dream_insight":
        return {"ok": False, "error": "wrong_proposal_kind", "id": insight_id}
    return resolve_proposal(
        active_store,
        insight_id,
        decision="approved",
        apply=lambda item: _save_approved_dream(item, cfg, active_store),
    )


def dream_reject_insight(
    insight_id: str,
    store: SuperMemoryStore | None = None,
    *,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Explicitly reject one pending proposal; terminal replay is a no-op."""
    cfg = load_config(config_path)
    active_store = store or SuperMemoryStore(cfg)
    proposal = get_proposal(active_store, insight_id)
    if proposal and proposal.get("kind") != "dream_insight":
        return {"ok": False, "error": "wrong_proposal_kind", "id": insight_id}
    result = resolve_proposal(active_store, insight_id, decision="rejected")
    # Preserve the legacy wrapper's "already resolved" response while the
    # shared resolver exposes the stronger idempotent-success contract.  The
    # explicit flags let newer callers distinguish this safe no-op from a
    # failed first transition.
    if result.get("idempotent") and result.get("no_op"):
        result["ok"] = False
        result["error"] = "already_resolved"
    if result.get("ok"):
        result["rejected"] = True
    return result


def dream_engine_status(store: SuperMemoryStore | None = None) -> dict[str, Any]:
    cfg = load_config()
    active_store = store or SuperMemoryStore(cfg)
    with readonly_connection(active_store) as conn:
        if conn is None:
            return {
                "ok": True,
                "total_memories": 0,
                "total_sessions": 0,
                "total_agents": 0,
                "memories_last_hour": 0,
                "phase1_surprisal": "ready",
                "phase2_patterns": "ready",
                "phase3_insights": "approval_required",
            }
        total = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0"
        ).fetchone()[0]
        sessions = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM memories WHERE session_id IS NOT NULL "
            "AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0"
        ).fetchone()[0]
        agents = conn.execute(
            "SELECT COUNT(DISTINCT agent_id) FROM memories WHERE agent_id IS NOT NULL "
            "AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0"
        ).fetchone()[0]
        last_hour = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE created_at > datetime('now', '-1 hour') "
            "AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0"
        ).fetchone()[0]
    return {
        "ok": True,
        "total_memories": total,
        "total_sessions": sessions,
        "total_agents": agents,
        "memories_last_hour": last_hour,
        "phase1_surprisal": "ready",
        "phase2_patterns": "ready",
        "phase3_insights": "approval_required",
    }
