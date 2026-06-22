"""Pipeline integration — connecting P0-P3 modules into save/recall flow.

Non-blocking: each integration is wrapped in try/except.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("super-memory.pipeline")

# ── Save Pipeline Extensions ─────────────────────────────────────────────

def run_safety_firewall(content: str) -> dict[str, Any]:
    """Run input firewall on auto-capture content."""
    try:
        from .safety.firewall import check_content, sanitize_explicit_content
        result = check_content(content)
        if result.blocked:
            logger.debug("firewall blocked content", reason=result.reason)
        return {"blocked": result.blocked, "reason": result.reason, "sanitized": result.sanitized}
    except Exception as e:
        logger.debug("firewall check failed (non-blocking)", error=str(e))
        return {"blocked": False}


def extract_relations(content: str) -> list[dict]:
    """Extract relation candidates from content for graph enrichment."""
    try:
        from .extraction.relations import extract_relations
        rels = extract_relations(content)
        return [
            {
                "source_span": r.source_span, "target_span": r.target_span,
                "relation_type": r.relation_type.value, "synapse_type": r.synapse_type,
                "confidence": r.confidence,
            }
            for r in rels
        ]
    except Exception as e:
        logger.debug("relations extraction failed (non-blocking)", error=str(e))
        return []


def detect_structure(content: str) -> dict | None:
    """Detect structured content (JSON, CSV, K=V, table)."""
    try:
        from .extraction.structure_detector import detect_structure
        result = detect_structure(content)
        if result:
            return {"format": result.format, "fields": result.fields[:5], "row_count": result.row_count}
        return None
    except Exception as e:
        logger.debug("structure detection failed (non-blocking)", error=str(e))
        return None


def check_triggers(content: str) -> list[dict]:
    """Check content against trigger patterns."""
    try:
        from .trigger_engine import check_triggers
        results = check_triggers(content)
        return [
            {"trigger_name": t.trigger_name, "trigger_type": t.trigger_type.value, "confidence": t.confidence}
            for t in results
        ]
    except Exception as e:
        logger.debug("trigger check failed (non-blocking)", error=str(e))
        return []


def enrich_with_relations(metadata: dict, content: str) -> dict:
    """Enrich metadata with relation and structure info."""
    rels = extract_relations(content)
    if rels:
        metadata.setdefault("extracted_relations", rels[:10])

    struct = detect_structure(content)
    if struct:
        metadata.setdefault("structured_format", struct["format"])
        if struct["fields"]:
            metadata.setdefault("structured_fields", struct["fields"])

    triggers = check_triggers(content)
    if triggers:
        metadata.setdefault("triggers", triggers)

    return metadata


# ── Recall Pipeline Extensions ───────────────────────────────────────────

def run_spreading_activation(
    query: str,
    store: Any,
    config: Any,
    anchor_neurons: list[str] | None = None,
    max_hops: int = 3,
) -> dict[str, Any]:
    """Run spreading activation as optional recall path."""
    try:
        from .spreading_activation import SpreadingActivation, should_stop_spreading
        conn = store.connect()
        sa = SpreadingActivation(conn, config)
        seeds = anchor_neurons or _find_seed_neurons(query, store)
        if not seeds:
            return {"activated": 0, "results": {}}
        results, trace = sa.activate(seeds, max_hops=max_hops)
        return {
            "activated": len(results),
            "top_neurons": sorted(results.keys(), key=lambda n: results[n].activation_level, reverse=True)[:10],
            "stopped_early": trace.stopped_early,
            "max_hop": trace.max_hop_used,
            "trace": {
                "new_per_hop": dict(trace.new_neurons_per_hop),
                "gain_per_hop": dict(trace.activation_gain_per_hop),
            },
        }
    except Exception as e:
        logger.debug("spreading activation failed (non-blocking)", error=str(e))
        return {"activated": 0, "error": str(e)}


def _find_seed_neurons(query: str, store: Any) -> list[str]:
    """Find seed neurons from query text for spreading activation."""
    try:
        with store.connect() as conn:
            terms = [t.strip().lower() for t in query.split() if len(t.strip()) > 2][:5]
            if not terms:
                return []
            neurons = []
            for term in terms:
                rows = conn.execute(
                    "SELECT id FROM cognitive_neurons WHERE content LIKE ? LIMIT 10",
                    (f"%{term}%",),
                ).fetchall()
                neurons.extend(r["id"] for r in rows)
            return list(set(neurons))[:20]
    except Exception as e:
        logger.debug("find seed neurons failed: %s", e)
        return []


def annotate_freshness(results: list[dict]) -> list[dict]:
    """Annotate recall results with freshness info."""
    try:
        from .safety.freshness import evaluate_freshness
        now = datetime.now(timezone.utc)
        for r in results:
            created = r.get("created_at")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    fr = evaluate_freshness(dt, now)
                    r["_freshness"] = {"level": fr.level.value, "score": fr.score, "age_days": fr.age_days}
                except Exception:
                    r["_freshness"] = {"level": "unknown", "score": 0.5}
        return results
    except Exception:
        return results


def load_warm_cache(store: Any) -> dict[str, float]:
    """Load cached activation states for warm-start recall."""
    try:
        from .cache import get_cache_manager
        cache = get_cache_manager(store)
        return cache.load_snapshot()
    except Exception:
        return {}


def save_warm_cache(store: Any, activations: dict[str, float]) -> None:
    """Save activation states after recall for warm-start."""
    try:
        from .cache import get_cache_manager
        cache = get_cache_manager(store)
        cache.save_snapshot(activations)
    except Exception:
        pass


def get_eternal_context(store: Any, level: int = 1) -> str:
    """Get eternal context for session start injection."""
    try:
        from .eternal_context import EternalContext
        ec = EternalContext(store)
        return ec.get_injection(level)
    except Exception as e:
        logger.debug("eternal context failed: %s", e)
        return ""
