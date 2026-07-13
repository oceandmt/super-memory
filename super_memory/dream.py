"""Dream Engine (P0) — consolidation dreaming for Super Memory.

Dreams are synthetic insight memories generated during off-peak consolidation.
They find latent patterns, strengthen weak connections, and propose novel
cross-domain associations without hallucinating false facts.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict, Counter
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .models import MemoryRecord, MemoryScope, MemoryType
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory

_DREAM_DRY_RUN_LIMIT = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store(config_path: str | None = None) -> SuperMemoryStore:
    cfg = load_config(config_path)
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    _init_tables(store)
    return store


def _init_tables(store: SuperMemoryStore) -> None:
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


def _remember_internal(content: str, mem_type: str, tags: list[str], config_path: str | None = None) -> dict[str, Any]:
    """Save a dream-derived memory through the canonical save pipeline.

    E1 quality gate: dream insights must pass a quality threshold and not
    duplicate an existing dream insight before being persisted. Returns a
    skip marker (no 'record') when gated out so callers treat it as no-save.
    """
    from . import bridge
    from .quality_scorer import score_memory
    import hashlib as _hl

    _MIN_OVERALL = 0.5
    _qs = score_memory(content, memory_type="insight")
    if _qs.overall < _MIN_OVERALL:
        return {"ok": False, "skipped": "low_quality", "quality_overall": _qs.overall}
    # Dedup against existing dream insights by content hash
    _h = _hl.sha256(content.encode()).hexdigest()
    try:
        store = _store(config_path)
        with store.connect() as _c:
            _dup = _c.execute(
                "SELECT 1 FROM memories WHERE type = 'insight' AND agent_id = 'dream-engine' "
                "AND json_extract(metadata_json,'$.dream_content_hash') = ? LIMIT 1",
                (_h,),
            ).fetchone()
        if _dup:
            return {"ok": False, "skipped": "duplicate"}
    except Exception:
        pass
    return bridge.remember({
        "content": content,
        "type": mem_type,
        "scope": MemoryScope.SHARED.value,
        "agent_id": "dream-engine",
        "project": "super-memory",
        "tags": tags,
        "source": "super-memory.dream",
        "trust_score": round(0.45 + 0.2 * _qs.overall, 3),
        "metadata": {
            "generated_by": "dream_engine",
            "dream_cycle": _now(),
            "dream_content_hash": _h,
            "quality_overall": _qs.overall,
        },
    }, config_path=config_path)


def _extract_keywords(text: str, top_n: int = 8) -> list[str]:
    """Deterministic keyword extraction: short words + frequency."""
    STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "on",
            "is", "are", "was", "were", "be", "by", "as", "this", "that", "it",
            "at", "from", "but", "not", "we", "they", "has", "have", "had", "do",
            "does", "did", "will", "would", "can", "could", "should", "may", "might"}
    tokens = [t.lower() for t in re.split(r"\W+", text) if len(t) > 3 and t.lower() not in STOP]
    common = [t for t, _ in Counter(tokens).most_common(top_n)]
    return common[:top_n]


def _jaccard_similarity(a: str, b: str) -> float:
    tokens_a = set(re.split(r"\W+", a.lower()))
    tokens_b = set(re.split(r"\W+", b.lower()))
    tokens_a.discard("")
    tokens_b.discard("")
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

# E2: dream noise + injection guard ─────────────────────────────────────────
# Generic/ambient tokens that produced the 20 rubbish "X appears in N memories"
# insights (license/copyright/software/...) and injection markers. Bridges or
# patterns keyed only on these are noise and must not become insight memories.
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
    """True when a candidate insight is ambient-token noise or injection echo.

    Blocks two failure modes seen in production:
    1. Insights keyed only on generic tokens (all shared keywords in blocklist).
    2. Insights whose text echoes the prompt-injection block.
    """
    low = (text or "").lower()
    if any(m in low for m in _DREAM_INJECTION_MARKERS):
        return True
    kws = {k.lower() for k in (keywords or []) if k}
    if kws and kws <= _DREAM_NOISE_TOKENS:
        # every shared keyword is a generic/ambient token → no real signal
        return True
    return False


def dream_insight_generation(limit=200, dry_run=True, config_path=None):
    """Dream Phase 1: Generate synthetic insights from latent patterns."""
    store = _store(config_path)
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    clusters = defaultdict(list)
    for row in rows:
        rec = row_to_memory(row)
        keywords = tuple(_extract_keywords(rec.content, top_n=5))
        if keywords:
            clusters[keywords].append({"id": rec.id, "content": rec.content, "type": rec.type.value, "layer": row["layer"], "keywords": keywords})

    candidates = []
    seen_pairs = set()
    cluster_list = list(clusters.values())
    for i, cluster_a in enumerate(cluster_list):
        if len(cluster_a) < 1:
            continue
        for item_a in cluster_a:
            for item_b in cluster_a[i+1:]:
                if item_b["id"] == item_a["id"]:
                    continue
                pair = (item_a["id"], item_b["id"]) if item_a["id"] < item_b["id"] else (item_b["id"], item_a["id"])
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                sim = _jaccard_similarity(item_a["content"], item_b["content"])
                if 0.15 < sim < 0.75:
                    shared_kw = set(item_a["keywords"]) & set(item_b["keywords"])
                    # E2: skip bridges whose only shared signal is ambient
                    # noise tokens or that echo injection content.
                    if shared_kw and not _is_dream_noise(
                        item_a["content"] + " " + item_b["content"], shared_kw
                    ):
                        candidates.append({
                            "source_a": {"id": item_a["id"], "content": item_a["content"][:160], "type": item_a["type"]},
                            "source_b": {"id": item_b["id"], "content": item_b["content"][:160], "type": item_b["type"]},
                            "cross_similarity": round(sim, 3),
                            "shared_keywords": list(shared_kw),
                            "proposed_insight": f"Bridge insight: {' and '.join(sorted(shared_kw))} connects {item_a['type']}->{item_b['type']} knowledge",
                        })

    candidates.sort(key=lambda c: c["cross_similarity"], reverse=True)
    insights = []
    created = []
    for cand in candidates[:10]:
        insight_content = (
            f"Dream insight: '{cand['proposed_insight']}' "
            f"(similarity={cand['cross_similarity']}, "
            f"from memories {cand['source_a']['id'][:12]} and {cand['source_b']['id'][:12]})"
        )
        insights.append(cand)
        if not dry_run:
            result = _remember_internal(
                content=insight_content,
                mem_type=MemoryType.INSIGHT.value,
                tags=["dream", "insight", f"bridge:{'_'.join(cand['shared_keywords'][:3])}"],
                config_path=config_path,
            )
            memory_id = result.get("record", {}).get("id")
            if memory_id:
                created.append(memory_id)

    if not dry_run:
        with store.connect() as conn:
            for cand in insights:
                conn.execute(
                    "INSERT INTO dream_events (id, kind, content, pattern_type, strength, source_text, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"dream:insight:{abs(hash(cand['proposed_insight'])) % 10**12}",
                        "insight",
                        cand["proposed_insight"],
                        "cross_domain_bridge",
                        cand["cross_similarity"],
                        json.dumps({"a": cand["source_a"]["id"], "b": cand["source_b"]["id"]}),
                        json.dumps({"keywords": cand["shared_keywords"]}),
                        _now(),
                    ),
                )

    return {
        "ok": True, "dry_run": dry_run, "clusters_found": len(clusters),
        "candidate_bridges": len(candidates), "insights_generated": len(insights),
        "memories_created": len(created), "insights": insights[:10],
    }


def dream_weak_tie_reinforcement(limit=200, dry_run=True, config_path=None):
    """Dream Phase 2: Strengthen weak but useful connections."""
    store = _store(config_path)
    with store.connect() as conn:
        try:
            weak_synapses = conn.execute(
                "SELECT * FROM cognitive_synapses WHERE weight < 0.3 AND weight > 0.05 ORDER BY weight ASC LIMIT ?",
                (limit // 2,),
            ).fetchall()
        except Exception:
            weak_synapses = []

    reinforced = []
    if not dry_run and weak_synapses:
        with store.connect() as conn:
            for syn in weak_synapses:
                new_weight = min(1.0, float(syn["weight"]) * 1.5)
                conn.execute(
                    "UPDATE cognitive_synapses SET weight=?, updated_at=? WHERE id=?",
                    (new_weight, _now(), syn["id"]),
                )
                reinforced.append({
                    "synapse_id": syn["id"],
                    "old_weight": syn["weight"],
                    "new_weight": new_weight,
                })

    return {
        "ok": True, "dry_run": dry_run,
        "weak_synapses_found": len(weak_synapses),
        "reinforced": reinforced[:50], "method": "weak_tie_boost_1.5x",
    }


def dream_pattern_summary(limit=200, dry_run=True, config_path=None):
    """Dream Phase 3: Generate summary patterns from repetitive content."""
    store = _store(config_path)
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    kw_counter = Counter()
    mem_by_kw = defaultdict(list)
    for row in rows:
        rec = row_to_memory(row)
        keywords = _extract_keywords(rec.content, top_n=6)
        seen_kw = set()
        for kw in keywords:
            kw_counter[kw] += 1
            if kw not in seen_kw:
                mem_by_kw[kw].append(rec.id)
                seen_kw.add(kw)

    patterns = []
    for kw, count in kw_counter.most_common(50):
        # E2: drop ambient/injection tokens — these produced the 20 rubbish
        # "'license' appears in N memories" insights that were soft-deleted.
        if kw.lower() in _DREAM_NOISE_TOKENS:
            continue
        if count >= 4 and len(set(mem_by_kw[kw])) >= 3:
            patterns.append({
                "keyword": kw, "frequency": count,
                "unique_memories": len(set(mem_by_kw[kw])),
                "sources": sorted(set(mem_by_kw[kw]))[:5],
            })

    # E1: token-frequency counts are statistics, not insights. We no longer
    # persist them as INSIGHT memories (they dominated recall with zero value
    # and amplified injection tokens). The phase now only *reports* frequency
    # patterns for observability; nothing is written to the canonical store.
    created_ids: list[str] = []

    return {
        "ok": True, "dry_run": dry_run,
        "unique_keywords_found": len(kw_counter),
        "patterns_detected": len(patterns),
        "patterns": patterns[:15],
        "memories_created": len(created_ids),
        "note": "token-frequency patterns are reported only, not persisted (E1)",
    }


def dream_full_cycle(limit=200, dry_run=True, config_path=None):
    """Run full Dream Engine cycle."""
    phase1 = dream_insight_generation(limit=limit, dry_run=dry_run, config_path=config_path)
    phase2 = dream_weak_tie_reinforcement(limit=limit, dry_run=dry_run, config_path=config_path)
    phase3 = dream_pattern_summary(limit=limit, dry_run=dry_run, config_path=config_path)
    return {
        "ok": True, "dry_run": dry_run, "mode": "full_dream_cycle",
        "phase1_insights": {"bridges_found": phase1["candidate_bridges"], "created": phase1["memories_created"]},
        "phase2_reinforcement": {"weak_synapses_found": phase2["weak_synapses_found"], "reinforced": len(phase2["reinforced"])},
        "phase3_patterns": {"patterns_detected": phase3["patterns_detected"], "created": phase3["memories_created"]},
        "total_memories_created": phase1["memories_created"] + phase3["memories_created"],
    }
