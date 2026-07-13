"""Dream Consolidation Engine (P0 #2) — idle-time memory consolidation.

Surprisal-based replay scheduler: during low-activity periods, replays recent
memories, detects cross-session patterns, consolidates related memories into
higher-level insights, and builds compressed representations.

Three-phase pipeline:
1. **Surprisal scoring** — rank memories by novelty (inverse frequency)
2. **Pattern detection** — cluster related memories across sessions
3. **Insight generation** — produce consolidated insight memories

Safety: all operations are dry-run by default; non-destructive soft-delete only.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .config import load_config
from .models import MemoryRecord, MemoryScope, MemoryType
from .storage import SuperMemoryStore, row_to_memory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jaccard_similarity(a: str, b: str) -> float:
    tokens_a = set(re.split(r"\W+", a.lower()))
    tokens_b = set(re.split(r"\W+", b.lower()))
    tokens_a.discard("")
    tokens_b.discard("")
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


# ── Phase 1: Surprisal Scoring ──────────────────────────────────────────────

def _token_frequencies(
    store: SuperMemoryStore,
    limit: int = 1000,
) -> dict[str, float]:
    """Build inverse token frequency over recent memories."""
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT content FROM memories ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    token_counts: Counter[str] = Counter()
    total = 0
    for (content,) in rows:
        tokens = set(re.split(r"\W+", content.lower()))
        tokens.discard("")
        for t in tokens:
            token_counts[t] += 1
        total += 1
    if total == 0:
        return {}
    return {t: math.log(total / max(1, c)) for t, c in token_counts.items()}


def _compute_surprisal(
    content: str,
    token_weights: dict[str, float],
) -> float:
    """Compute surprisal score: average inverse-frequency of tokens."""
    tokens = re.split(r"\W+", content.lower())
    tokens = [t for t in tokens if t]
    if not tokens:
        return 0.0
    scores = [token_weights.get(t, math.log(1000)) for t in tokens]
    return sum(scores) / len(scores)


def rank_by_surprisal(
    store: SuperMemoryStore,
    limit: int = 200,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """Rank memories by surprisal (novelty)."""
    token_weights = _token_frequencies(store, limit=limit)
    with store.connect() as conn:
        rows = conn.execute(
            """SELECT id, content, type, agent_id, session_id, created_at
               FROM memories
               WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    scored: list[dict[str, Any]] = []
    for row in rows:
        s = _compute_surprisal(row["content"], token_weights)
        scored.append({
            "id": row["id"],
            "content": row["content"][:200],
            "type": row["type"],
            "agent_id": row["agent_id"],
            "session_id": row["session_id"],
            "surprisal": round(s, 3),
        })
    scored.sort(key=lambda x: x["surprisal"], reverse=True)
    return scored


# ── Phase 2: Pattern Detection ──────────────────────────────────────────────

def detect_patterns(
    store: SuperMemoryStore,
    window_hours: int = 24,
    min_cluster_size: int = 2,
    similarity_threshold: float = 0.4,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """Detect cross-session patterns by clustering related memories.

    Groups similar memories across different sessions using Jaccard similarity,
    then labels each cluster as a potential consolidated insight.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    with store.connect() as conn:
        rows = conn.execute(
            """SELECT id, content, type, agent_id, session_id, created_at
               FROM memories WHERE created_at > ?
               AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0
               ORDER BY created_at DESC LIMIT 500""",
            (cutoff,),
        ).fetchall()

    # Build clusters
    clusters: list[dict[str, Any]] = []
    used: set[str] = set()
    for i, a in enumerate(rows):
        if a["id"] in used:
            continue
        group = [dict(a)]
        used.add(a["id"])
        for b in rows[i + 1 :]:
            if b["id"] in used:
                continue
            if _jaccard_similarity(a["content"], b["content"]) >= similarity_threshold:
                group.append(dict(b))
                used.add(b["id"])
        if len(group) >= min_cluster_size:
            # Check if cluster spans multiple sessions (genuine cross-session pattern)
            sessions = set(m["session_id"] for m in group if m["session_id"])
            clusters.append({
                "size": len(group),
                "sessions": len(sessions),
                "cross_session": len(sessions) > 1,
                "content_samples": [m["content"][:150] for m in group[:3]],
                "agent_ids": list(set(m["agent_id"] for m in group if m["agent_id"])),
                "memory_ids": [m["id"] for m in group],
                "avg_surprisal": round(sum(
                    _compute_surprisal(m["content"], {})
                    for m in group
                ) / len(group), 3),
            })
    clusters.sort(key=lambda x: x["size"], reverse=True)
    return clusters


# ── Phase 3: Insight Generation ─────────────────────────────────────────────

def generate_insight(
    cluster: dict[str, Any],
) -> str:
    """Generate a consolidated insight from a cluster of related memories.

    Uses extractive summarization: picks the longest/highest-surprisal content
    and prefixes with a session-span label.
    """
    samples = cluster.get("content_samples", [])
    if not samples:
        return ""
    # Pick the longest sample as the representative
    best = max(samples, key=len)
    cross = "Cross-session" if cluster.get("cross_session") else "Single-session"
    insight = (
        f"[Dream Consolidation] {cross} pattern — {cluster['size']} related memories"
        f" across {cluster['sessions']} session(s). "
        f"Key insight: {best}"
    )
    return insight


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
    """Run the full dream consolidation cycle.

    Three-phase pipeline:
    1. Surprisal scoring → rank memories by novelty
    2. Pattern detection → cluster related memories across sessions
    3. Insight generation → produce consolidated insights

    In dry-run mode, reports candidates without saving.
    In live mode, saves insights as MEMORY records.
    """
    report: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "window_hours": window_hours,
        "phases": {},
    }

    # Phase 1: Surprisal scoring
    ranked = rank_by_surprisal(store, limit=200, dry_run=dry_run)
    report["phases"]["surprisal"] = {
        "memories_scored": len(ranked),
        "top_surprisal": ranked[:5] if ranked else [],
    }

    # Phase 2: Pattern detection
    clusters = detect_patterns(
        store,
        window_hours=window_hours,
        min_cluster_size=min_cluster_size,
        similarity_threshold=similarity_threshold,
        dry_run=dry_run,
    )
    report["phases"]["patterns"] = {
        "clusters_found": len(clusters),
        "clusters": clusters[:max_insights],
    }

    # Phase 3: Insight generation & save
    insights_saved = 0
    insights: list[dict[str, Any]] = []
    for cluster in clusters[:max_insights]:
        insight_text = generate_insight(cluster)
        insights.append({
            "content": insight_text[:500],
            "cluster_size": cluster["size"],
            "cross_session": cluster["cross_session"],
            "source_memory_ids": cluster["memory_ids"],
        })

    report["phases"]["insights"] = {
        "candidates": insights,
        "would_save": len(insights) if dry_run else 0,
    }

    # Live mode: save insights (or, when require_review, enqueue for approval)
    if not dry_run and insights:
        from .config import load_config as _lc
        from .service import SuperMemoryService
        from .quality_scorer import score_memory
        import hashlib as _hl
        cfg = _lc(config_path)
        svc = SuperMemoryService(cfg)
        # E1 quality gate: threshold + dedup against existing dream insights
        _MIN_OVERALL = 0.5
        _seen_hashes: set[str] = set()
        _gate_stats = {"skipped_low_quality": 0, "skipped_dup": 0}
        try:
            with store.connect() as _c:  # type: ignore
                for _r in _c.execute(
                    "SELECT content FROM memories WHERE type = 'insight' AND agent_id = 'dream-engine'"
                ).fetchall():
                    _txt = _r[0] if not hasattr(_r, "keys") else _r["content"]
                    _seen_hashes.add(_hl.sha256((_txt or "").encode()).hexdigest())
        except Exception:
            pass
        for ins in insights:
            _content = ins["content"]
            # E2: reject ambient-token noise and injection echoes before save.
            try:
                from .dream import _is_dream_noise as _dn
                if _dn(_content):
                    _gate_stats.setdefault("skipped_noise", 0)
                    _gate_stats["skipped_noise"] += 1
                    continue
            except Exception:
                pass
            _h = _hl.sha256(_content.encode()).hexdigest()
            if _h in _seen_hashes:
                _gate_stats["skipped_dup"] += 1
                continue
            _qs = score_memory(_content, memory_type="insight")
            if _qs.overall < _MIN_OVERALL:
                _gate_stats["skipped_low_quality"] += 1
                continue
            record = MemoryRecord(
                content=_content,
                type=MemoryType.INSIGHT,
                scope=MemoryScope.PROJECT,
                agent_id="dream-engine",
                tags=["dream-consolidation", "p0", "insight"],
                metadata={
                    "dream_cluster_size": ins["cluster_size"],
                    "dream_cross_session": ins["cross_session"],
                    "dream_source_ids": ins["source_memory_ids"],
                    "dream_generated_at": _now(),
                    "quality_overall": _qs.overall,
                },
            )
            try:
                if require_review:
                    # E11: don't persist as a live memory; enqueue for human/agent
                    # approval. dream_approve_insight() later saves it verbatim.
                    _enqueue_pending_insight(store, ins, quality_overall=_qs.overall)
                    _seen_hashes.add(_h)
                    _gate_stats.setdefault("queued_for_review", 0)
                    _gate_stats["queued_for_review"] += 1
                else:
                    svc.save(record)
                    _seen_hashes.add(_h)
                    insights_saved += 1
            except Exception:
                pass
        report["phases"]["insights"]["saved"] = insights_saved
        report["phases"]["insights"]["quality_gate"] = _gate_stats
        if require_review:
            report["phases"]["insights"]["require_review"] = True
            report["phases"]["insights"]["queued"] = _gate_stats.get("queued_for_review", 0)

    report["insights_saved"] = insights_saved
    return report

# ── E11: dream insight review-before-save queue ─────────────────────────────

def _init_pending_insights(store: SuperMemoryStore) -> None:
    with store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dream_pending_insights (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                cluster_size INTEGER NOT NULL DEFAULT 0,
                cross_session INTEGER NOT NULL DEFAULT 0,
                source_memory_ids TEXT,
                quality_overall REAL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dream_pending_status ON dream_pending_insights(status)"
        )


def _enqueue_pending_insight(store: SuperMemoryStore, ins: dict[str, Any], *, quality_overall: float | None = None) -> str:
    """Persist a candidate insight for later approval (idempotent by content hash)."""
    import hashlib as _hl
    _init_pending_insights(store)
    content = ins["content"]
    chash = _hl.sha256(content.encode()).hexdigest()
    pid = str(uuid4())
    with store.connect() as conn:
        # dedup: skip if an unresolved copy already queued
        existing = conn.execute(
            "SELECT id FROM dream_pending_insights WHERE content_hash=? AND status='pending'",
            (chash,),
        ).fetchone()
        if existing:
            return existing[0] if not hasattr(existing, "keys") else existing["id"]
        conn.execute(
            "INSERT INTO dream_pending_insights "
            "(id, content, content_hash, cluster_size, cross_session, source_memory_ids, quality_overall, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (
                pid, content, chash,
                int(ins.get("cluster_size", 0)),
                1 if ins.get("cross_session") else 0,
                json.dumps(ins.get("source_memory_ids", [])),
                quality_overall,
                _now(),
            ),
        )
    return pid


def dream_list_pending_insights(store: SuperMemoryStore | None = None, *, limit: int = 50, config_path: str | None = None) -> dict[str, Any]:
    """List insights awaiting review (E11)."""
    cfg = load_config(config_path)
    store = store or SuperMemoryStore(cfg)
    _init_pending_insights(store)
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT id, content, cluster_size, cross_session, source_memory_ids, quality_overall, created_at "
            "FROM dream_pending_insights WHERE status='pending' ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r) if hasattr(r, "keys") else {}
        try:
            d["source_memory_ids"] = json.loads(d.get("source_memory_ids") or "[]")
        except Exception:
            d["source_memory_ids"] = []
        d["cross_session"] = bool(d.get("cross_session"))
        items.append(d)
    return {"ok": True, "pending": items, "count": len(items)}


def dream_approve_insight(insight_id: str, store: SuperMemoryStore | None = None, *, config_path: str | None = None) -> dict[str, Any]:
    """Approve a pending insight and persist it as a canonical memory (E11)."""
    from .service import SuperMemoryService
    cfg = load_config(config_path)
    store = store or SuperMemoryStore(cfg)
    _init_pending_insights(store)
    with store.connect() as conn:
        row = conn.execute(
            "SELECT * FROM dream_pending_insights WHERE id=? AND status='pending'",
            (insight_id,),
        ).fetchone()
    if not row:
        return {"ok": False, "error": "not_found_or_already_resolved", "id": insight_id}
    d = dict(row)
    try:
        src_ids = json.loads(d.get("source_memory_ids") or "[]")
    except Exception:
        src_ids = []
    record = MemoryRecord(
        content=d["content"],
        type=MemoryType.INSIGHT,
        scope=MemoryScope.PROJECT,
        agent_id="dream-engine",
        tags=["dream-consolidation", "p0", "insight", "reviewed"],
        metadata={
            "dream_cluster_size": d.get("cluster_size"),
            "dream_cross_session": bool(d.get("cross_session")),
            "dream_source_ids": src_ids,
            "dream_generated_at": _now(),
            "quality_overall": d.get("quality_overall"),
            "review_status": "approved",
        },
    )
    svc = SuperMemoryService(cfg)
    saved = svc.save(record)
    with store.connect() as conn:
        conn.execute(
            "UPDATE dream_pending_insights SET status='approved', resolved_at=? WHERE id=?",
            (_now(), insight_id),
        )
    return {"ok": True, "id": insight_id, "saved": True, "result": getattr(saved, "__dict__", str(saved))}


def dream_reject_insight(insight_id: str, store: SuperMemoryStore | None = None, *, config_path: str | None = None) -> dict[str, Any]:
    """Reject a pending insight so it is never persisted (E11)."""
    cfg = load_config(config_path)
    store = store or SuperMemoryStore(cfg)
    _init_pending_insights(store)
    with store.connect() as conn:
        cur = conn.execute(
            "UPDATE dream_pending_insights SET status='rejected', resolved_at=? WHERE id=? AND status='pending'",
            (_now(), insight_id),
        )
        changed = cur.rowcount
    if not changed:
        return {"ok": False, "error": "not_found_or_already_resolved", "id": insight_id}
    return {"ok": True, "id": insight_id, "rejected": True}


# ── Wiring helper for maintenance_run() ─────────────────────────────────────

def dream_engine_status(store: SuperMemoryStore | None = None) -> dict[str, Any]:
    """Check dream engine infrastructure status."""
    from .config import load_config as _lc
    cfg = _lc()
    store = store or SuperMemoryStore(cfg)
    with store.connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM memories "
            "WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0"
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
        "phase3_insights": "ready",
    }
