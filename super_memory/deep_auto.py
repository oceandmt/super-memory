"""Auto Deep pipeline — Audit, Qualify, Debug, Improve for Super Memory.

Runs comprehensive health checks, qualification scoring, debugging,
and improvement proposals without requiring an LLM.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from typing import Any

from .config import load_config
from .models import MemoryRecord, MemoryScope, MemoryType
from .service import SuperMemoryService
from .storage import SuperMemoryStore, row_to_memory


def _now():
    return datetime.now(timezone.utc).isoformat()


def _store(config_path=None):
    cfg = load_config(config_path)
    SuperMemoryService(cfg)
    store = SuperMemoryStore(cfg)
    return store


# ── PHASE 1: DEEP AUDIT ──────────────────────────────────────────────────────

def deep_audit(config_path=None):
    """Comprehensive audit of memory health, consistency, and quality.

    Checks:
    1. Canonical-first compliance
    2. Layer distribution balance
    3. Orphan/duplicate detection
    4. Type diversity
    5. Project coverage
    6. Agent routing tags
    7. Content quality heuristics
    """
    cfg = load_config(config_path)
    store = _store(config_path)
    from . import bridge

    total = 0
    layer_counts = Counter()
    type_counts = Counter()
    scope_counts = Counter()
    agent_counts = Counter()
    project_counts = Counter()
    content_lens = []
    duplicates = []
    soft_deleted = 0
    missing_tags = 0
    no_agent_tag = 0

    with store.connect() as conn:
        rows = conn.execute("SELECT * FROM memories").fetchall()
        total = len(rows)
        active_memory_ids: set[str] = set()
        canonical_memory_ids: set[str] = set()
        canonical_content_lens: list[int] = []
        unresolved_long_canonical_lens: list[int] = []
        mitigated_long_memories = 0
        for row in rows:
            rec = row_to_memory(row)
            is_soft_deleted = bool(rec.metadata.get("soft_deleted"))
            layer_counts[row["layer"]] += 1
            type_counts[rec.type.value] += 1
            scope_counts[rec.scope.value] += 1
            agent_counts[rec.agent_id] += 1
            p = rec.project or "(none)"
            project_counts[p] += 1
            content_lens.append(len(rec.content))

            if is_soft_deleted:
                soft_deleted += 1
            else:
                active_memory_ids.add(rec.id)
                if row["layer"] == "workspace_markdown":
                    canonical_memory_ids.add(rec.id)
                    clen = len(rec.content)
                    canonical_content_lens.append(clen)
                    if clen > 2000:
                        if rec.metadata.get("compression_policy") == "verbatim_drawers_plus_summary" and rec.metadata.get("canonical_retained"):
                            mitigated_long_memories += 1
                        else:
                            unresolved_long_canonical_lens.append(clen)

            norm_tags = set(rec.normalized_tags())
            if not any(t.startswith("agent:") for t in norm_tags):
                no_agent_tag += 1

        # Duplicate content detection should not count intentional 4-layer mirrors
        # as duplicates. Restrict to active canonical workspace_markdown rows.
        content_map = defaultdict(list)
        for row in rows:
            rec = row_to_memory(row)
            if rec.metadata.get("soft_deleted") or row["layer"] != "workspace_markdown":
                continue
            norm = " ".join(re.split(r"\W+", rec.content.lower().strip()))
            if len(norm) > 20:
                content_map[norm].append(rec.id)
        duplicates = [{"ids": ids, "count": len(ids)} for norm, ids in content_map.items() if len(set(ids)) > 1]

    canonical_count = len(canonical_memory_ids)
    total_active = len(active_memory_ids)
    canonical_compliance_pct = round(canonical_count / max(total_active, 1) * 100, 1)
    avg_len = sum(content_lens) / max(1, len(content_lens))
    max_len = max(content_lens) if content_lens else 0
    # Long-memory audit tracks unresolved active canonical source records only.
    # Canonical long records that have been split into verbatim drawers +
    # semantic closets are counted as mitigated because canonical content is
    # intentionally retained for provenance.
    long_memories = len(unresolved_long_canonical_lens)

    audit = {
        "total_memories": total,
        "active_memories": total_active,
        "soft_deleted": soft_deleted,
        "canonical_markdown_count": canonical_count,
        "canonical_compliance_pct": canonical_compliance_pct,
        "layers": dict(layer_counts),
        "types": dict(type_counts),
        "scopes": dict(scope_counts),
        "agents": dict(agent_counts),
        "projects": dict(project_counts.most_common(20)),
        "avg_content_length": round(avg_len, 1),
        "max_content_length": max_len,
        "long_memories_over_2k": long_memories,
        "mitigated_long_memories_over_2k": mitigated_long_memories,
        "duplicate_clusters": len(duplicates),
        "duplicates": duplicates[:10],
        "memories_without_agent_tag": no_agent_tag,
    }

    issues = []
    if audit["canonical_compliance_pct"] < 50:
        issues.append({"severity": "high", "issue": "Low canonical markdown compliance", "detail": f"Only {audit['canonical_compliance_pct']}% of memories have workspace_markdown layer"})
    if audit["duplicate_clusters"] > 5:
        issues.append({"severity": "medium", "issue": f"{audit['duplicate_clusters']} duplicate clusters found", "detail": "Run consolidation dedup"})
    if audit["long_memories_over_2k"] > 10:
        issues.append({"severity": "low", "issue": f"{audit['long_memories_over_2k']} memories over 2000 chars", "detail": "Consider compression"})
    if audit["memories_without_agent_tag"] > 5:
        issues.append({"severity": "low", "issue": f"{audit['memories_without_agent_tag']} memories missing agent tag", "detail": "Routing may be incomplete"})

    return {
        "ok": True, "audit": audit, "issues": issues,
        "health_score": round(max(0, 100 - 25 * len(issues)), 1),
        "grade": "A" if len(issues) == 0 else "B" if len(issues) <= 2 else "C" if len(issues) <= 5 else "D",
    }


# ── PHASE 2: DEEP QUALIFY ────────────────────────────────────────────────────

def deep_qualify(config_path=None):
    """Score the quality of memories and recall pipeline.

    Measures:
    - Type distribution health (too many 'context' = under-typed)
    - Agent balance
    - Recall relevance (via sampling)
    - Content quality signals

    NOTE: Memories saved across 4 layers produce 4 rows each.  All aggregate
    ratios use a DISTINCT id count as denominator so layer replication does
    not inflate percentages.
    """
    store = _store(config_path)
    with store.connect() as conn:
        rows = conn.execute("SELECT * FROM memories WHERE COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0").fetchall()

    total_rows = len(rows)
    if total_rows == 0:
        return {"ok": True, "grade": "N/A", "score": 0, "note": "No active memories to qualify"}

    # Unique memory ID tracking — these are the canonical "one memory" count
    seen: dict[str, MemoryRecord] = {}
    for row in rows:
        mem_id = row["id"]
        if mem_id not in seen:
            seen[mem_id] = row_to_memory(row)

    unique_active = len(seen)
    type_counts: Counter = Counter()
    agent_counts: Counter = Counter()
    scope_counts: Counter = Counter()
    has_projects = 0
    has_trust = 0
    content_lens_workspace: list[int] = []

    for mem_id, rec in seen.items():
        type_counts[rec.type.value] += 1
        agent_counts[rec.agent_id] += 1
        scope_counts[rec.scope.value] += 1
        if rec.project:
            has_projects += 1
        if rec.trust_score is not None:
            has_trust += 1
        # Use workspace_markdown row length for canonical size
        for row in rows:
            if row["id"] == mem_id and row["layer"] == "workspace_markdown":
                content_lens_workspace.append(len(row["content"]))
                break
        else:
            # Fallback: any layer
            for row in rows:
                if row["id"] == mem_id:
                    content_lens_workspace.append(len(row["content"]))
                    break

    # Type diversity score — denominator is unique active count
    type_diversity = len(type_counts)
    context_ratio = type_counts.get("context", 0) / max(unique_active, 1)
    durable_ratio = sum(type_counts.get(t, 0) for t in ["decision", "workflow", "preference", "doctrine", "lesson", "fact"]) / max(unique_active, 1)

    # Project coverage
    project_coverage = has_projects / max(unique_active, 1)

    # Trust coverage
    trust_coverage = has_trust / max(unique_active, 1)

    # Average content length (workspace canonical rows only)
    avg_len = sum(content_lens_workspace) / max(1, len(content_lens_workspace))
    too_short = sum(1 for l in content_lens_workspace if l < 20)
    too_short_ratio = too_short / max(len(content_lens_workspace), 1)

    # Scoring
    score = 50.0
    reasons = []

    if durable_ratio >= 0.15:
        score += 15
        reasons.append(f"good durable type ratio ({durable_ratio:.0%})")
    elif durable_ratio >= 0.10:
        score += 10
        reasons.append(f"moderate durable ratio ({durable_ratio:.0%})")
    else:
        score -= 10
        reasons.append(f"low durable type ratio ({durable_ratio:.0%})")

    if context_ratio <= 0.50:
        score += 10
        reasons.append(f"context ratio controlled ({context_ratio:.0%})")
    else:
        score -= 5
        reasons.append(f"high context ratio ({context_ratio:.0%})")

    if project_coverage >= 0.3:
        score += 10
        reasons.append(f"good project coverage ({project_coverage:.0%})")
    if trust_coverage >= 0.2:
        score += 5
        reasons.append(f"trust score usage ({trust_coverage:.0%})")
    if too_short_ratio <= 0.1:
        score += 5
        reasons.append(f"low too-short ratio ({too_short_ratio:.0%})")
    else:
        score -= 5
    if 30 <= avg_len <= 2000:
        score += 5
        reasons.append(f"healthy avg length ({avg_len:.0f} chars)")

    score = min(100, max(0, score))
    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 50 else "D"

    return {
        "ok": True,
        "grade": grade,
        "score": round(score, 1),
        "reasons": reasons,
        "type_diversity": type_diversity,
        "durable_ratio": round(durable_ratio, 4),
        "context_ratio": round(context_ratio, 4),
        "project_coverage": round(project_coverage, 4),
        "trust_coverage": round(trust_coverage, 4),
        "too_short_ratio": round(too_short_ratio, 4),
        "avg_length": round(avg_len, 1),
        "agent_counts": dict(agent_counts.most_common(10)),
        "type_counts": dict(type_counts.most_common(10)),
    }


# ── PHASE 3: DEEP DEBUG ──────────────────────────────────────────────────────

def deep_debug(config_path=None):
    """Find operational issues and misconfigurations.

    Checks:
    - Database integrity
    - Missing table errors
    - Pending sync records
    - Graph projection orphans
    - Cross-layer inconsistencies
    - Stale/expired entries
    """
    cfg = load_config(config_path)
    store = _store(config_path)

    problems = []
    warnings_list = []

    with store.connect() as conn:
        # Check for schema issues
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        expected_tables = {
            "memories", "honcho_events", "cognitive_neurons", "cognitive_synapses",
            "cognitive_fibers", "cognitive_hypotheses", "cognitive_evidence",
            "cognitive_predictions", "palace_drawers", "intelligence_events",
            "lifecycle_state", "dream_events", "telemetry_events", "telemetry_daily",
            "agent_isolation_rules", "autocomplete_index", "short_term_reviews",
            "semantic_index",
        }
        missing_tables = expected_tables - tables
        if missing_tables:
            warnings_list.append(f"Tables not yet created (normal for fresh DB): {len(missing_tables)}")

        # Pending sync
        pending = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE pending_canonical_sync=1"
        ).fetchone()["c"]
        if pending > 0:
            problems.append({"severity": "high", "issue": f"{pending} records pending canonical sync", "fix": "run flush_pending()"})

        # Soft-deleted
        deleted = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE json_extract(metadata_json, '$.soft_deleted')=1"
        ).fetchone()["c"]
        if deleted > 0:
            warnings_list.append(f"{deleted} soft-deleted records (normal)")

        # Graph orphans
        try:
            orphans = conn.execute(
                "SELECT COUNT(*) as c FROM cognitive_neurons WHERE source_memory_id IS NOT NULL AND source_memory_id NOT IN (SELECT id FROM memories)"
            ).fetchone()["c"]
            if orphans > 0:
                problems.append({"severity": "medium", "issue": f"{orphans} orphan graph neurons", "fix": "run graph_cleanup_orphans()"})
        except Exception:
            pass

        # Overdue predictions
        try:
            overdue = conn.execute(
                "SELECT COUNT(*) as c FROM cognitive_predictions WHERE status='active' AND deadline IS NOT NULL AND deadline < ?",
                (_now(),),
            ).fetchone()["c"]
            if overdue > 0:
                problems.append({"severity": "low", "issue": f"{overdue} overdue predictions", "fix": "run expire_predictions()"})
        except Exception:
            pass

    return {
        "ok": True,
        "problems": problems,
        "warnings": warnings_list,
        "problem_count": len(problems),
        "warning_count": len(warnings_list),
        "fix_suggestions": [p["fix"] for p in problems],
    }


# ── PHASE 4: DEEP IMPROVE ────────────────────────────────────────────────────

def deep_improve(dry_run=True, config_path=None):
    """Generate and optionally apply improvement proposals.

    Based on audit + qualify + debug results, proposes fixes:
    - Consolidation for duplicates
    - Type promotion for under-typed content
    - Project tagging for untagged memories
    - Graph rebuild for missing projections
    """
    cfg = load_config(config_path)
    store = _store(config_path)
    from . import bridge

    audit_result = deep_audit(config_path=config_path)
    qualify_result = deep_qualify(config_path=config_path)
    debug_result = deep_debug(config_path=config_path)

    improvements = []
    applied = []

    # 1. Fix untagged memories
    if audit_result["audit"]["memories_without_agent_tag"] > 0:
        improvements.append({
            "action": "tag_memories",
            "target": f"{audit_result['audit']['memories_without_agent_tag']} memories",
            "proposal": "Add agent tags to untagged memories",
            "priority": "low",
        })
        if not dry_run:
            with store.connect() as conn:
                updated = 0
                rows = conn.execute("SELECT * FROM memories").fetchall()
                for row in rows:
                    tags = set(json.loads(row["tags_json"]))
                    if not any(t.startswith("agent:") for t in tags):
                        tags.add(f"agent:{row['agent_id']}")
                        esc_tags = json.dumps(sorted(tags)).replace("'", "''")
                        conn.executescript(f"UPDATE memories SET tags_json='{esc_tags}' WHERE id='{row['id']}' AND layer='{row['layer']}';")
                        updated += 1
                applied.append({"action": "tag_memories", "ok": True, "updated": updated})

    # 2. Promote context to decision where applicable
    if qualify_result.get("context_ratio", 0) > 0.5:
        improvements.append({
            "action": "type_promotion",
            "target": "high-context memories",
            "proposal": "Promote frequent context with decision/blocker signals",
            "priority": "medium",
        })
        # Implementation in bridge

    # 3. Graph rebuild if orphans
    orphan_issues = [p for p in debug_result["problems"] if "orphan" in p.get("issue", "")]
    if orphan_issues:
        improvements.append({
            "action": "graph_cleanup",
            "target": str(orphan_issues[0].get("issue", "unknown")),
            "proposal": "Run graph_cleanup_orphans to remove stale projections",
            "priority": "medium",
        })
        if not dry_run:
            try:
                result = bridge.graph_cleanup_orphans(config_path=config_path)
                applied.append({"action": "graph_cleanup", "result": result})
            except Exception as exc:
                applied.append({"action": "graph_cleanup", "ok": False, "error": str(exc)})

    # 4. Prediction expiry
    pred_issues = [p for p in debug_result["problems"] if "prediction" in p.get("issue", "")]
    if pred_issues:
        improvements.append({
            "action": "expire_predictions",
            "target": str(pred_issues[0].get("issue", "unknown")),
            "proposal": "Expire overdue predictions",
            "priority": "low",
        })
        if not dry_run:
            from . import reasoning
            result = reasoning.expire_predictions(config_path=config_path)
            applied.append({"action": "expire_predictions", "ok": bool(result.get("ok")), "result": result})

    # 5. Run consolidation if duplicates
    if audit_result["audit"]["duplicate_clusters"] > 0:
        improvements.append({
            "action": "dedup_consolidation",
            "target": f"{audit_result['audit']['duplicate_clusters']} clusters",
            "proposal": "Merge duplicate memories via consolidation",
            "priority": "medium",
        })
        if not dry_run:
            from . import consolidation
            result = consolidation.consolidate_real(strategy="dedup", dry_run=False, config_path=config_path)
            applied.append({"action": "dedup_consolidation", "ok": bool(result.get("ok")), "result": result})

    applied_ok = all(bool(item.get("ok", True)) for item in applied)
    return {
        "ok": applied_ok,
        "dry_run": dry_run,
        "audit_grade": audit_result["grade"],
        "qualify_score": qualify_result.get("score", 0),
        "qualify_grade": qualify_result.get("grade", "N/A"),
        "problems_found": debug_result["problem_count"],
        "improvement_proposals": improvements,
        "applied": applied if not dry_run else [],
        "summary": f"Audit grade {audit_result['grade']}, Qualify score {qualify_result.get('score', 0):.0f}, {len(improvements)} improvements proposed{' (dry run)' if dry_run else ''}",
    }


# ── COMPOSITE: FULL AUTO DEEP PIPELINE ────────────────────────────────────────

def auto_deep_pipeline(dry_run=True, config_path=None):
    """Run full Auto Deep pipeline: Audit → Qualify → Debug → Improve."""
    audit = deep_audit(config_path=config_path)
    qualify = deep_qualify(config_path=config_path)
    debug_result = deep_debug(config_path=config_path)
    improve = deep_improve(dry_run=dry_run, config_path=config_path)

    sub_ok = all(bool(part.get("ok", True)) for part in (audit, qualify, debug_result, improve))
    return {
        "ok": sub_ok,
        "pipeline": "auto_deep",
        "dry_run": dry_run,
        "audit": audit,
        "qualify": qualify,
        "debug": debug_result,
        "improve": improve,
        "overall_grade": audit["grade"],
        "overall_score": round((audit["health_score"] + qualify.get("score", 0)) / 2, 1),
        "pipeline_summary": (
            f"Audit: {audit['grade']} ({audit['health_score']}/100), "
            f"Qualify: {qualify.get('grade', 'N/A')} ({qualify.get('score', 0):.0f}/100), "
            f"Debug: {debug_result['problem_count']} problems, "
            f"Improve: {len(improve['improvement_proposals'])} proposals "
            f"{'(dry run)' if dry_run else ' (applied)'}"
        ),
    }
