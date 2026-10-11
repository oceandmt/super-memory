"""Prioritized P0-P3 enhancement plan and operator runbook.

This module is intentionally deterministic and dependency-light so it can be
surfaced from CLI/MCP/tests without touching live memory state.  It captures the
next implementation wave for Super Memory: critical hardening, retrieval
quality, governance, and operationalization.
"""

from __future__ import annotations

from typing import Any


def _item(priority: str, title: str, objective: str, deliverables: list[str], tests: list[str], commands: list[str], tools: list[str]) -> dict[str, Any]:
    return {
        "priority": priority,
        "title": title,
        "objective": objective,
        "deliverables": deliverables,
        "suggested_tests": tests,
        "operational_commands": commands,
        "operational_tools": tools,
    }


def prioritized_enhancement_plan() -> dict[str, Any]:
    """Return the canonical P0-P3 enhancement plan plus runbook guidance."""
    plan = [
        _item(
            "P0",
            "Production safety and lifecycle hardening",
            "Make memory capture, writes, migrations, and destructive operations safe by default.",
            [
                "Run write-gate validation for all new memory envelopes.",
                "Keep migration/preflight/release gates as required deployment checks.",
                "Ensure forget/edit operations preserve audit provenance and never hard-delete without an explicit purge path.",
                "Keep capture failures non-fatal but observable through diagnostics.",
            ],
            [
                "pytest tests/test_super_memory_consistency_regressions.py tests/test_openclaw_plugin_guardrails.py",
                "pytest tests/test_p0_p5_edge_cases.py tests/test_phase11_sanitize.py",
                "python scripts/super_memory_preflight.py",
                "python scripts/super_memory_release_gate.py",
            ],
            [
                "super-memory doctor",
                "super-memory recommendations --json-out",
                "python scripts/super_memory_preflight.py",
                "python scripts/super_memory_release_gate.py",
            ],
            [
                "super_memory_health",
                "super_memory_diagnostics",
                "super_memory_conflicts",
                "super_memory_status",
            ],
        ),
        _item(
            "P1",
            "Hybrid recall quality and ranking",
            "Improve recall beyond keyword search with deterministic routing, provenance, and ranking evidence.",
            [
                "Use FTS/vector/graph candidates where available and rank by exactness, recency, trust, scope, and source authority.",
                "Return provenance and why-selected evidence for every recall item.",
                "Prevent a single source layer from silently dominating results.",
                "Keep SQLite FTS as fallback when semantic/vector dependencies are unhealthy.",
            ],
            [
                "pytest tests/test_retrieval_pipeline.py tests/test_hybrid_search.py tests/test_reranker.py",
                "pytest tests/test_recall_security_quality.py tests/test_recall_lifecycle_quality.py",
                "pytest tests/test_autocomplete_recommendations.py",
            ],
            [
                "super-memory recommendations --limit 10 --json-out",
                "super-memory autocomplete-rebuild",
                "super-memory recall-benchmark",
                "python scripts/benchmark_spreading_activation.py",
            ],
            [
                "super_memory_recall",
                "super_memory_prefetch",
                "super_memory_recommendations",
                "super_memory_semantic_doctor",
            ],
        ),
        _item(
            "P2",
            "Belief governance, conflicts, and graph consistency",
            "Surface contradictory or stale beliefs and keep graph/projection layers aligned with canonical memory.",
            [
                "Extract normalized claims for conflict candidates.",
                "Group conflicts with status: open, accepted_both, superseded, resolved.",
                "Record resolution provenance and optional replacement memories.",
                "Audit graph/projection drift and recommend repair actions.",
            ],
            [
                "pytest tests/test_extraction.py tests/test_extraction_relations.py tests/test_extraction_structure.py",
                "pytest tests/test_p4_graph_v2.py tests/test_vector_graph_validation.py",
                "pytest tests/test_cross_agent_p0_p2.py tests/test_diagnostics.py",
            ],
            [
                "super-memory recommendations --json-out",
                "python scripts/check_sql_safety.py",
                "python scripts/audit.py",
                "python scripts/merge_content_hash_duplicates.py --dry-run",
            ],
            [
                "super_memory_conflicts",
                "super_memory_consolidate",
                "super_memory_provenance",
                "super_memory_cross_layer_health",
            ],
        ),
        _item(
            "P3",
            "Session archive, compression, and operator runbooks",
            "Keep long-running sessions resumable without token bloat and make operations inspectable.",
            [
                "Compress long sessions into summaries, decisions, blockers, and action items.",
                "Keep raw event lineage searchable while startup context remains bounded.",
                "Publish operator commands/tools for routine maintenance and release checks.",
                "Maintain final go/no-go recommendations from health, benchmark, and drift signals.",
            ],
            [
                "pytest tests/test_semantic_short_term_maintenance.py tests/test_eternal_context.py",
                "pytest tests/test_performance_smoke.py tests/test_phase8_live_readiness.py",
                "pytest tests/test_improvement_roadmap.py tests/test_autocomplete_recommendations.py",
            ],
            [
                "super-memory recommendations --limit 10",
                "super-memory durable-pack-audit --pack-name default --fix false",
                "python scripts/deep_qualify_final.py",
                "python scripts/export_tool_catalog.py",
            ],
            [
                "super_memory_context",
                "super_memory_situation",
                "super_memory_stats",
                "super_memory_recommendations",
            ],
        ),
    ]
    return {
        "ok": True,
        "plan": plan,
        "recommended_next": [
            "Run P0 release/preflight gates before deploying any memory lifecycle changes.",
            "Run P1 recall benchmark after ranking or backend changes.",
            "Run P2 conflict/drift diagnostics weekly or before large imports.",
            "Run P3 archive/diagnostic checks for long-lived Discord/Telegram sessions.",
        ],
        "final_recommendation": "Proceed P0→P3 in order: safety gates first, recall quality second, conflict/graph governance third, and session/runbook operationalization fourth. Treat failing P0 gates as deploy blockers; P1-P3 failures should create targeted follow-up cards unless they affect data integrity.",
    }
