from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from typing import Any, Callable

from . import bridge
from .config import load_config
from .mempalace.tools import MemPalaceTools, MEMPALACE_TOOLS
from .honcho.tools import HonchoTools, HONCHO_TOOLS
from .cross_agent import CrossAgentTools, CROSS_AGENT_TOOLS
from .session_timeline import SessionTimelineTools, SESSION_TIMELINE_TOOLS
from .capture_hook import CaptureHook, CAPTURE_HOOK_TOOLS
from .handoff import HandoffTools, HANDOFF_TOOLS
from .synthesis import SynthesisTools, SYNTHESIS_TOOLS
from .hooks import HookManager, HOOKS_TOOLS
from .hybrid_recall import HybridRecall, HYBRID_RECALL_TOOLS
from .claim_extractor import ClaimExtractor, CLAIM_EXTRACTOR_TOOLS
from .session_archive import SessionArchive, SESSION_ARCHIVE_TOOLS
from .reports import Reports, REPORTS_TOOLS
from .execution_tools_definitions import EXECUTION_TOOLS
from . import mcp_execution_tools

JSON = dict[str, Any]

SERVER_INFO = {"name": "super-memory", "version": "0.1.0"}
PROTOCOL_VERSION = "2024-11-05"
MCP_PROFILE = "normal"

NORMAL_TOOLS = {
    "super_memory_remember",
    "super_memory_remember_batch",
    "super_memory_show",
    "super_memory_context",
    "super_memory_todo",
    "super_memory_auto",
    "super_memory_stats",
    "super_memory_health",
    "super_memory_sanitize_prompt",
    "super_memory_sanitize_auto_capture",
    "super_memory_normalize_memory",
    "super_memory_recall",
    "super_memory_prefetch",
    "super_memory_sync_turn",
    "super_memory_memory_search",
    "super_memory_memory_get",
    "super_memory_status",
    "super_memory_index_sessions",
    "super_memory_session_index_status",
    "super_memory_search_sessions",
    "super_memory_cooldown_status",
    "super_memory_cooldown_clear",
    # P1 Search Quality
    "super_memory_hybrid_fuse",
    "super_memory_diversify_results",
    "super_memory_temporal_decay",
    "super_memory_session_boost",
    # P2 Embedding Providers
    "super_memory_list_embedding_providers",
    "super_memory_embed_text",
    # P3 Infrastructure
    "super_memory_rem_search",
    "super_memory_rem_health",
    "super_memory_watcher_scan",
    "super_memory_flush_plan_status",
    "super_memory_flush_session_memories",
    "super_memory_reindex_all",
    # Remaining Gap Tools
    "super_memory_get_index_identity",
    "super_memory_set_index_identity",
    "super_memory_self_heal_embeddings",
    "super_memory_self_heal_status",
    "super_memory_write_contract_process_jobs",
    "super_memory_write_contract_reconcile",
    "super_memory_write_contract_semantic_merge",
    "super_memory_maintenance_enqueue",
    "super_memory_maintenance_job_status",
    "super_memory_maintenance_process_jobs",
    "super_memory_build_prompt_section",
    "super_memory_generate_narrative",
    "super_memory_rem_extract_all",
    "super_memory_qmd_search",
    "super_memory_qmd_health",
    "super_memory_qmd_start",
    "super_memory_qmd_stop",
    "super_memory_watcher_settle_scan",
    # Micro-gap 3: Batch State
    "super_memory_batch_state_status",
    "super_memory_reset_batch_state",
    # Micro-gap 4: Reindex FSM
    "super_memory_reindex_fsm_status",
    # Micro-gap 8: FTS-only reindex
    "super_memory_reindex_fts_only",
    # Micro-gap 5: Sync Interval
    "super_memory_sync_interval_status",
    "super_memory_sync_interval_start",
    "super_memory_sync_interval_stop",
    "super_memory_sync_startup_catchup",
    # Micro-gap 6: Read-only Recovery
    "super_memory_recovery_status",
    "super_memory_reset_recovery_state",
    # Execution Patterns (v2.4.0)
    "super_memory_route_task",
    "super_memory_create_execution_contract",
    "super_memory_create_plan",
    "super_memory_update_plan_progress",
    "super_memory_recover_incomplete_tasks",
    "super_memory_detect_memory_loss",
}
ADMIN_TOOLS = NORMAL_TOOLS | {"super_memory_promote"}
ADVANCED_TOOLS = {
    "super_memory_conflicts",
    "super_memory_provenance",
    "super_memory_source",
    "super_memory_version",
    "super_memory_pin",
    "super_memory_consolidate",
    "super_memory_gaps",
    "super_memory_explain",
    "super_memory_situation",
    "super_memory_reflex",
    "super_memory_boundaries",
    "super_memory_train",
    "super_memory_import",
    "super_memory_index",
    "super_memory_sync",
    "super_memory_telegram_backup",
    "super_memory_visualize",
    "super_memory_store",
    "super_memory_watch",
    "super_memory_working_memory_get",
    "super_memory_working_memory_set",
    "super_memory_attention_score",
    "super_memory_route_memory",
    "super_memory_parallel_save",
    "super_memory_recall_arbitrate",
    "super_memory_consolidation_cycle",
    "super_memory_conflict_resolve",
    "super_memory_promotion_candidates",
    "super_memory_feedback_outcome",
    "super_memory_graph_stats",
    "super_memory_graph_neighbors",
    "super_memory_graph_recall",
    "super_memory_spreading_activation_recall",
    "nmem_recall",
    "super_memory_graph_rebuild",
    "super_memory_graph_cleanup_orphans",
    "super_memory_dedup_neurons",
    "super_memory_hypothesis_create",
    "super_memory_hypothesis_get",
    "super_memory_hypothesis_list",
    "super_memory_evidence_add",
    "super_memory_prediction_create",
    "super_memory_prediction_list",
    "super_memory_verify_prediction",
    "super_memory_lifecycle_review",
    "super_memory_lifecycle_cache",
    "super_memory_lifecycle_tier",
    "super_memory_lifecycle_compression",
    "super_memory_reflex_status",
    "super_memory_leitner",
    # MemPalace Phase 1 tools
    "super_memory_palace_search",
    "super_memory_palace_load_layer",
    "super_memory_palace_wings",
    "super_memory_palace_rooms",
    "super_memory_palace_halls",
    "super_memory_palace_drawers",
    "super_memory_palace_summary",
    "super_memory_palace_startup_context",
    "super_memory_palace_extract",
    # Honcho Phase 2 tools
    "super_memory_honcho_ask",
    "super_memory_honcho_context",
    "super_memory_honcho_profile",
    "super_memory_honcho_conclude",
    "super_memory_honcho_search",
    "super_memory_honcho_analyze_turn",
    "super_memory_honcho_sessions",
    "super_memory_train_local",
    "super_memory_index_local",
    "super_memory_index_status",
    "super_memory_import_local",
    "super_memory_watch_scan",
    "super_memory_sync_status",
    "super_memory_store_status",
    "super_memory_diagnostics",
    "super_memory_memory_slot_contract",
    "super_memory_mcp_contract",
    "super_memory_supervised_runtime_smoke",
    # Cross-agent / cross-session Phase A+B+C tools
    "super_memory_cross_agent_recall",
    "super_memory_cross_agent_honcho_ask",
    "super_memory_cross_agent_summary",
    "super_memory_cross_agent_compare",
    "super_memory_list_agents",
    "super_memory_session_timeline",
    "super_memory_session_list",
    "super_memory_session_evolution",
    "super_memory_session_search",
    "super_memory_capture_event",
    "super_memory_capture_turn",
    "super_memory_create_handoff",
    "super_memory_get_handoff",
    "super_memory_list_handoffs",
    "super_memory_update_handoff_status",
    "super_memory_cross_session_synthesis",
    "super_memory_shared_recall",
    "super_memory_promote_to_shared",
    "super_memory_cross_agent_conflicts",
    # P0-P5 Optimization tools
    "super_memory_post_turn_capture",
    "super_memory_session_start_context",
    "super_memory_session_end_summary",
    "super_memory_delegation_handoff",
    "super_memory_cross_scope_recall",
    "super_memory_extract_claims",
    "super_memory_find_contradictions",
    "super_memory_resolve_contradiction",
    "super_memory_agent_belief_report",
    "super_memory_create_session_summary",
    "super_memory_get_session_summary",
    "super_memory_list_session_summaries",
    "super_memory_search_session_archives",
    "super_memory_session_timeline_view",
    "super_memory_auto_handoff_on_spawn",
    "super_memory_load_current_handoff",
    "super_memory_complete_handoff_with_outcome",
    "super_memory_cross_agent_report",
    "super_memory_cross_layer_health",
    "super_memory_session_health",
    "super_memory_memory_pollution_report",
    "super_memory_export_memory_graph",
    # Dream Engine (P0)
    "super_memory_dream_insight_generation",
    "super_memory_dream_weak_tie_reinforcement",
    "super_memory_dream_pattern_summary",
    "super_memory_dream_full_cycle",
    # Telemetry (P3)
    "super_memory_telemetry_record_event",
    "super_memory_telemetry_stats",
    "super_memory_telemetry_aggregate_daily",
    # Per-agent Isolation (P3)
    "super_memory_isolation_set_rules",
    "super_memory_isolation_get_rules",
    "super_memory_isolation_summary",
    "super_memory_isolation_agent_counts",
    # Auto-complete
    "super_memory_autocomplete_suggest",
    "super_memory_autocomplete_idle",
    "super_memory_autocomplete_rebuild",
    "super_memory_autocomplete_status",
    "super_memory_recommendations",
    # Auto Deep pipeline
    "super_memory_deep_audit",
    "super_memory_deep_qualify",
    "super_memory_deep_debug",
    "super_memory_deep_improve",
    "super_memory_auto_deep_pipeline",
    # P0 fixes: forget + edit
    "super_memory_forget",
    "super_memory_edit",
    # P0: MemoryEnvelope
    "super_memory_build_envelope",
    "super_memory_remember_through_envelope",
    # P0: SourceAdapter
    "super_memory_ingest_through_adapter",
    "super_memory_list_source_adapters",
    "super_memory_ingest_and_remember",
    # P0: Semantic Closets/Drawers
    "super_memory_build_closets",
    "super_memory_rebuild_all_closets",
    "super_memory_search_closets",
    "super_memory_hydrate_drawers",
    "super_memory_closet_stats",
    # P0: Recall Arbitration v3
    "super_memory_recall_arbitrate_v3",
    "super_memory_recall_quick",
    # P0: Recall Feedback Loop
    "super_memory_recall_record_event",
    "super_memory_recall_record_feedback",
    "super_memory_recall_record_correction",
    "super_memory_recall_feedback_stats",
    "super_memory_recall_generate_training_cases",
    "super_memory_recall_benchmark_seed",
    "super_memory_recall_release_gate",
    "super_memory_scheduled_maintenance_report",
    # P2: Projection Drift Repair
    "super_memory_audit_drift",
    "super_memory_repair_orphans",
    "super_memory_full_drift_repair",
    "super_memory_register_projection",
    # P2: Adapter-driven Watcher
    "super_memory_adapter_scan_once",
    "super_memory_adapter_settle_scan",
    "super_memory_adapter_monitor_status",
    # P2: Line Citations / Neighbor Expansion
    "super_memory_enrich_recall_with_citations",
    "super_memory_track_source",
    # P2: Agentic Dialectic Mode
    "super_memory_dialectic_answer",
    # P2: Self-Education Curriculum
    "super_memory_analyze_recall_failures",
    "super_memory_generate_curriculum",
    "super_memory_run_benchmark_tests",
}
ADMIN_TOOLS = ADMIN_TOOLS | ADVANCED_TOOLS

# B5: curated profile. Biggest context savings vs. `admin` (236 tools) while
# preserving the day-to-day workflow: core read/write, recall, the deep_*
# maintenance suite, consolidation/diagnostics, and the internal capture tools
# OpenClaw invokes for auto-capture (capture_event/capture_turn) — omitting
# those would silently break memory capture under the curated profile.
CURATED_TOOLS = {
    # core read/write
    "super_memory_remember",
    "super_memory_remember_batch",
    "super_memory_recall",
    "super_memory_prefetch",
    "super_memory_show",
    "super_memory_edit",
    "super_memory_forget",
    "super_memory_context",
    "super_memory_todo",
    "super_memory_pin",
    "super_memory_promote",
    # status / quality
    "super_memory_status",
    "super_memory_stats",
    "super_memory_health",
    "super_memory_situation",
    "super_memory_recommendations",
    "super_memory_memory_pollution_report",
    # search / compatibility
    "super_memory_memory_search",
    "super_memory_memory_get",
    "super_memory_search_sessions",
    # capture (invoked internally by OpenClaw)
    "super_memory_sync_turn",
    "super_memory_capture_event",
    "super_memory_capture_turn",
    # maintenance / deep suite
    "super_memory_consolidate",
    "super_memory_diagnostics",
    "super_memory_graph_stats",
    "super_memory_maintenance_process_jobs",
    "super_memory_maintenance_job_status",
    "super_memory_deep_audit",
    "super_memory_deep_qualify",
    "super_memory_deep_debug",
    "super_memory_deep_improve",
    "super_memory_auto_deep_pipeline",
}


def _text(content: Any) -> list[JSON]:
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, indent=2)
    return [{"type": "text", "text": content}]


def _schema(properties: JSON, required: list[str] | None = None) -> JSON:
    return {"type": "object", "properties": properties, "required": required or []}


TOOLS: dict[str, JSON] = {
    "super_memory_remember": {
        "description": "Save a memory through Super Memory canonical-first layer order.",
        "inputSchema": _schema(
            {
                "content": {"type": "string"},
                "type": {"type": "string", "default": "context"},
                "scope": {"type": "string", "default": "session"},
                "agent_id": {"type": "string", "default": "lucas"},
                "session_id": {"type": "string"},
                "project": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "source": {"type": "string"},
                "trust_score": {"type": "number"},
                "metadata": {"type": "object"},
                "config_path": {"type": "string"},
            },
            ["content"],
        ),
    },
    "super_memory_remember_batch": {
        "description": "Save multiple memories through the same canonical-first layer order; partial failures stay per item.",
        "inputSchema": _schema(
            {
                "memories": {"type": "array", "items": {"type": "object"}, "maxItems": 20},
                "config_path": {"type": "string"},
            },
            ["memories"],
        ),
    },
    "super_memory_show": {
        "description": "Show a memory by id across derived Super Memory layers without changing canonical markdown.",
        "inputSchema": _schema({"memory_id": {"type": "string"}, "config_path": {"type": "string"}}, ["memory_id"]),
    },
    "super_memory_context": {
        "description": "Get recent or query-relevant Super Memory context from the merged layer view.",
        "inputSchema": _schema(
            {
                "query": {"type": "string", "default": ""},
                "limit": {"type": "integer", "default": 10},
                "config_path": {"type": "string"},
            }
        ),
    },
    "super_memory_todo": {
        "description": "Save a TODO memory through canonical-first layer order.",
        "inputSchema": _schema(
            {
                "task": {"type": "string"},
                "priority": {"type": "integer", "default": 5},
                "config_path": {"type": "string"},
            },
            ["task"],
        ),
    },
    "super_memory_auto": {
        "description": "Extract simple memory candidates from text and optionally save them canonical-first.",
        "inputSchema": _schema(
            {
                "text": {"type": "string"},
                "save": {"type": "boolean", "default": False},
                "config_path": {"type": "string"},
            },
            ["text"],
        ),
    },
    "super_memory_stats": {
        "description": "Alias of status for neural-memory-style stats consumers.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_diagnostics": {
        "description": "Phase 8 diagnostics dashboard for canonical-first, sqlite, graph, lifecycle, and safe optional states.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_memory_slot_contract": {
        "description": "Run Phase 8 memory-slot replacement contract: save/search/get/show/graph projection.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_mcp_contract": {
        "description": "Verify MCP stdio tools/list exposure for required Super Memory tools.",
        "inputSchema": _schema({"profile": {"type": "string", "default": "admin"}, "config_path": {"type": "string"}}),
    },
    "super_memory_supervised_runtime_smoke": {
        "description": "Run local supervised no-live-config Phase 8 runtime smoke.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_list_agents": {
        "description": "List known agent ids that have memories in the store, with per-agent counts.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_health": {
        "description": "Check Super Memory consistency guardrails: canonical-first and workspace markdown enabled.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_cross_layer_health": {
        "description": "Cross-layer parity/health report: per-layer counts, sqlite-only ids, and content drift across memory layers.",
        "inputSchema": _schema({"config_path": {"type": "string"}, "parity_threshold": {"type": "integer"}}),
    },
    "super_memory_sanitize_prompt": {
        "description": "Sanitize recall/prompt text by redacting common secrets and normalizing whitespace/control characters.",
        "inputSchema": _schema({"text": {"type": "string"}}, ["text"]),
    },
    "super_memory_sanitize_auto_capture": {
        "description": "Sanitize text before auto-capture storage.",
        "inputSchema": _schema({"text": {"type": "string"}}, ["text"]),
    },
    "super_memory_normalize_memory": {
        "description": "Normalize a memory payload schema without saving it.",
        "inputSchema": _schema({"memory": {"type": "object"}, "auto_capture": {"type": "boolean", "default": False}}, ["memory"]),
    },
    "super_memory_recall": {
        "description": "Recall memories from Super Memory layers.",
        "inputSchema": _schema(
            {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
                "config_path": {"type": "string"},
            },
            ["query"],
        ),
    },
    "super_memory_prefetch": {
        "description": "Merged/deduped Super Memory recall for prompt prefetch.",
        "inputSchema": _schema(
            {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
                "config_path": {"type": "string"},
            },
            ["query"],
        ),
    },
    "super_memory_sync_turn": {
        "description": "Save a compact multi-agent conversation turn event.",
        "inputSchema": _schema(
            {
                "agent_id": {"type": "string", "default": "lucas"},
                "session_id": {"type": "string"},
                "user_message": {"type": "string"},
                "assistant_message": {"type": "string"},
                "project": {"type": "string"},
                "metadata": {"type": "object"},
                "config_path": {"type": "string"},
            }
        ),
    },
    "super_memory_memory_search": {
        "description": "OpenClaw memory_search-compatible recall payload from Super Memory.",
        "inputSchema": _schema(
            {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
                "min_score": {"type": "number", "default": 0},
                "corpus": {"type": "string", "default": "all"},
                "config_path": {"type": "string"},
            },
            ["query"],
        ),
    },
    "super_memory_memory_get": {
        "description": "OpenClaw memory_get-compatible read from Super Memory virtual paths or workspace files.",
        "inputSchema": _schema(
            {
                "path": {"type": "string"},
                "from_line": {"type": "integer", "default": 1},
                "lines": {"type": "integer", "default": 20},
                "corpus": {"type": "string", "default": "all"},
                "config_path": {"type": "string"},
            },
            ["path"],
        ),
    },
    "super_memory_promote": {
        "description": "Promote a memory to MEMORY.md and the matching register.",
        "inputSchema": _schema({"memory_id": {"type": "string"}, "config_path": {"type": "string"}}, ["memory_id"]),
    },
    "super_memory_status": {
        "description": "Show Super Memory local status.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_index_sessions": {
        "description": "Index all session transcript files into FTS5 for corpus='sessions' search.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_session_index_status": {
        "description": "Get session transcript index health status (files indexed, chunks, chars).",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_search_sessions": {
        "description": "Search session transcripts via FTS5 index, returning memory-core compatible results.",
        "inputSchema": _schema({
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
            "min_score": {"type": "number", "default": 0.0},
            "config_path": {"type": "string"},
        }, ["query"]),
    },
    "super_memory_cooldown_status": {
        "description": "Get cooldown manager status (active entries count).",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_cooldown_clear": {
        "description": "Clear all cooldown entries (reset unavailable state).",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    # ── P1: Search Quality ──────────────────────────────────────
    "super_memory_hybrid_fuse": {
        "description": "RRF-fuse text and vector search results for hybrid ranking.",
        "inputSchema": _schema({
            "text_results": {"type": "array", "items": {"type": "object"}},
            "vector_results": {"type": "array", "items": {"type": "object"}},
            "text_weight": {"type": "number", "default": 0.5},
            "vector_weight": {"type": "number", "default": 0.5},
            "top_k": {"type": "integer"},
        }, ["text_results", "vector_results"]),
    },
    "super_memory_diversify_results": {
        "description": "MMR-diversify search results for non-redundant ranking.",
        "inputSchema": _schema({
            "results": {"type": "array", "items": {"type": "object"}},
            "query": {"type": "string"},
            "top_k": {"type": "integer"},
            "lambda_param": {"type": "number", "default": 0.7},
        }, ["results", "query"]),
    },
    "super_memory_temporal_decay": {
        "description": "Apply exponential temporal decay to search result scores.",
        "inputSchema": _schema({
            "results": {"type": "array", "items": {"type": "object"}},
            "corpus": {"type": "string", "default": "memory"},
            "half_life": {"type": "number"},
        }, ["results"]),
    },
    "super_memory_session_boost": {
        "description": "Boost search results from the current session.",
        "inputSchema": _schema({
            "results": {"type": "array", "items": {"type": "object"}},
            "current_session_id": {"type": "string"},
            "boost_factor": {"type": "number", "default": 0.3},
        }, ["results"]),
    },
    # ── P2: Embedding Providers ───────────────────────────────────
    "super_memory_list_embedding_providers": {
        "description": "List all embedding providers with availability status.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_embed_text": {
        "description": "Embed text to vector using the best available provider.",
        "inputSchema": _schema({
            "text": {"type": "string"},
            "dimensions": {"type": "integer"},
            "config_path": {"type": "string"},
        }, ["text"]),
    },
    # ── P3: Infrastructure ───────────────────────────────────────
    "super_memory_rem_search": {
        "description": "REM nearest-neighbour vector search via sqlite_vec or numpy brute-force.",
        "inputSchema": _schema({
            "query_vector": {"type": "array", "items": {"type": "number"}},
            "top_k": {"type": "integer", "default": 10},
            "min_score": {"type": "number", "default": 0.0},
            "config_path": {"type": "string"},
        }, ["query_vector"]),
    },
    "super_memory_rem_health": {
        "description": "REM health check (vector count).",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_watcher_scan": {
        "description": "One-shot file watcher scan for changed markdown files.",
        "inputSchema": _schema({
            "directories": {"type": "array", "items": {"type": "string"}},
            "exclude": {"type": "array", "items": {"type": "string"}},
            "config_path": {"type": "string"},
        }),
    },
    "super_memory_flush_plan_status": {
        "description": "Get flush plan status (pending session→project memories).",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_flush_session_memories": {
        "description": "Execute flush: promote session-scoped memories to project scope.",
        "inputSchema": _schema({
            "limit": {"type": "integer", "default": 100},
            "config_path": {"type": "string"},
        }),
    },
    "super_memory_reindex_all": {
        "description": "Atomic rebuild of all FTS5 + vector indices.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    # ── Remaining Gaps ────────────────────────────────────────
    "super_memory_get_index_identity": {
        "description": "Get index identity (which embedding provider built the index).",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_set_index_identity": {
        "description": "Record which embedding provider built the index.",
        "inputSchema": _schema({
            "provider_id": {"type": "string"},
            "model": {"type": "string", "default": ""},
            "dimensions": {"type": "integer", "default": 384},
            "config_path": {"type": "string"},
        }, ["provider_id"]),
    },
    "super_memory_self_heal_embeddings": {
        "description": "Auto-detect and repair memories missing embeddings.",
        "inputSchema": _schema({
            "batch_size": {"type": "integer", "default": 50},
            "config_path": {"type": "string"},
        }),
    },
    "super_memory_self_heal_status": {
        "description": "Show self-heal status (count of memories missing vectors).",
        "inputSchema": _schema({"config_path": {"type": "string"}, "mode": {"type": "string", "default": "fast"}}),
    },
    "super_memory_write_contract_process_jobs": {
        "description": "Process write-contract outbox jobs (embedding/projection workers).",
        "inputSchema": _schema({"limit": {"type": "integer", "default": 50}, "config_path": {"type": "string"}}),
    },
    "super_memory_write_contract_reconcile": {
        "description": "Reconcile write-contract integrity gaps and enqueue repair jobs.",
        "inputSchema": _schema({"limit": {"type": "integer", "default": 200}, "config_path": {"type": "string"}}),
    },
    "super_memory_write_contract_semantic_merge": {
        "description": "Soft-delete normalized/semantic near-duplicate canonical memories.",
        "inputSchema": _schema({"threshold": {"type": "number", "default": 0.92}, "simhash_distance": {"type": "integer", "default": 3}, "limit": {"type": "integer", "default": 500}, "dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}),
    },
    "super_memory_duplicate_resolution_v2": {
        "description": "Resolve duplicate clusters with canonical selection and soft-delete cleanup.",
        "inputSchema": _schema({"threshold": {"type": "number", "default": 0.92}, "simhash_distance": {"type": "integer", "default": 3}, "limit": {"type": "integer", "default": 500}, "dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}),
    },
    "super_memory_self_improvement_orchestrator": {
        "description": "Run full self-improvement cycle: audit, qualify, debug, benchmark, safe fixes, snapshot, lesson.",
        "inputSchema": _schema({"dry_run": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 500}, "remember_lesson": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}),
    },
    "super_memory_project_backfill": {
        "description": "Infer and backfill missing project metadata for active memories.",
        "inputSchema": _schema({"limit": {"type": "integer", "default": 2000}, "dry_run": {"type": "boolean", "default": True}, "rebuild_graph": {"type": "boolean", "default": False}, "config_path": {"type": "string"}}),
    },
    "super_memory_project_synapse_backfill": {
        "description": "Infer missing project metadata and rebuild project synapses.",
        "inputSchema": _schema({"limit": {"type": "integer", "default": 2000}, "dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}),
    },
    "super_memory_maintenance_enqueue": {
        "description": "Enqueue an async maintenance job.",
        "inputSchema": _schema({"job_type": {"type": "string"}, "args": {"type": "object"}, "config_path": {"type": "string"}}, ["job_type"]),
    },
    "super_memory_maintenance_job_status": {
        "description": "Get async maintenance job status/result.",
        "inputSchema": _schema({"job_id": {"type": "string"}, "config_path": {"type": "string"}}, ["job_id"]),
    },
    "super_memory_maintenance_process_jobs": {
        "description": "Process async maintenance jobs.",
        "inputSchema": _schema({"limit": {"type": "integer", "default": 5}, "config_path": {"type": "string"}}),
    },
    "super_memory_build_prompt_section": {
        "description": "Build markdown memory context section from search results.",
        "inputSchema": _schema({
            "results": {"type": "array", "items": {"type": "object"}},
            "title": {"type": "string", "default": "Memory Context"},
            "max_tokens": {"type": "integer", "default": 4000},
            "include_citations": {"type": "boolean", "default": True},
        }, ["results"]),
    },
    "super_memory_generate_narrative": {
        "description": "Generate dreaming narrative markdown document from cognitive insights.",
        "inputSchema": _schema({
            "title": {"type": "string", "default": "Dreaming Narrative"},
            "out_dir": {"type": "string"},
            "max_insights": {"type": "integer", "default": 10},
            "config_path": {"type": "string"},
        }),
    },
    "super_memory_rem_extract_all": {
        "description": "Extract REM evidence from all session transcripts.",
        "inputSchema": _schema({
            "min_confidence": {"type": "number", "default": 0.6},
            "promote": {"type": "boolean", "default": True},
            "config_path": {"type": "string"},
        }),
    },
    "super_memory_qmd_search": {
        "description": "Search via QMD Meilisearch binary (external search).",
        "inputSchema": _schema({
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        }, ["query"]),
    },
    "super_memory_qmd_health": {
        "description": "QMD health check (binary available, running).",
        "inputSchema": _schema({}),
    },
    "super_memory_qmd_start": {
        "description": "Start QMD Meilisearch binary.",
        "inputSchema": _schema({}),
    },
    "super_memory_qmd_stop": {
        "description": "Stop QMD Meilisearch binary.",
        "inputSchema": _schema({}),
    },
    "super_memory_watcher_settle_scan": {
        "description": "Debounced file scan with settle detection (waits for writes to finish).",
        "inputSchema": _schema({
            "directories": {"type": "array", "items": {"type": "string"}},
            "exclude": {"type": "array", "items": {"type": "string"}},
            "config_path": {"type": "string"},
        }),
    },
    # Micro-gap 3: Batch State
    "super_memory_batch_state_status": {
        "description": "Get batch operation failure tracking state.",
        "inputSchema": _schema({}),
    },
    "super_memory_reset_batch_state": {
        "description": "Reset batch failure state counter.",
        "inputSchema": _schema({}),
    },
    # Micro-gap 4: Reindex FSM
    "super_memory_reindex_fsm_status": {
        "description": "Get reindex Finite State Machine status.",
        "inputSchema": _schema({}),
    },
    # Micro-gap 8: FTS-only reindex
    "super_memory_reindex_fts_only": {
        "description": "Rebuild only FTS5 indices, skip vectors.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    # Micro-gap 5: Sync Interval + Startup Catchup
    "super_memory_sync_interval_status": {
        "description": "Get sync interval manager status (interval, dirty sources, last sync).",
        "inputSchema": _schema({}),
    },
    "super_memory_sync_interval_start": {
        "description": "Start periodic background sync with startup catchup.",
        "inputSchema": _schema({}),
    },
    "super_memory_sync_interval_stop": {
        "description": "Stop periodic background sync.",
        "inputSchema": _schema({}),
    },
    "super_memory_sync_startup_catchup": {
        "description": "Run startup catchup — sync missed changes since last run.",
        "inputSchema": _schema({}),
    },
    # Micro-gap 6: Read-only Recovery
    "super_memory_recovery_status": {
        "description": "Get DB recovery state (attempts, last error, recovered).",
        "inputSchema": _schema({"db_path": {"type": "string"}}),
    },
    "super_memory_reset_recovery_state": {
        "description": "Reset DB recovery state count.",
        "inputSchema": _schema({"db_path": {"type": "string"}}),
    },
}

for _tool in MEMPALACE_TOOLS + HONCHO_TOOLS + CROSS_AGENT_TOOLS + SESSION_TIMELINE_TOOLS + CAPTURE_HOOK_TOOLS + HANDOFF_TOOLS + SYNTHESIS_TOOLS + HOOKS_TOOLS + HYBRID_RECALL_TOOLS + CLAIM_EXTRACTOR_TOOLS + SESSION_ARCHIVE_TOOLS + REPORTS_TOOLS + EXECUTION_TOOLS:
    TOOLS[_tool["name"]] = {
        "description": _tool["description"],
        "inputSchema": _tool["inputSchema"],
    }

for _name, _desc, _props in [
    ("super_memory_conflicts", "Detect/list deterministic conflict candidates.", {"content": {"type": "string"}, "memory_id": {"type": "string"}, "config_path": {"type": "string"}}),
    ("super_memory_provenance", "Trace/verify/approve memory provenance.", {"memory_id": {"type": "string"}, "action": {"type": "string", "default": "trace"}, "actor": {"type": "string", "default": "super-memory"}, "config_path": {"type": "string"}}),
    ("super_memory_source", "Register an external source metadata record.", {"name": {"type": "string"}, "source_type": {"type": "string"}, "version": {"type": "string"}, "status": {"type": "string"}, "metadata": {"type": "object"}, "config_path": {"type": "string"}}),
    ("super_memory_version", "Create/list lightweight memory version snapshots.", {"action": {"type": "string", "default": "create"}, "name": {"type": "string", "default": "snapshot"}, "description": {"type": "string"}, "limit": {"type": "integer", "default": 20}, "config_path": {"type": "string"}}),
    ("super_memory_pin", "Record pin/unpin intent for a memory.", {"memory_id": {"type": "string"}, "action": {"type": "string", "default": "pin"}, "config_path": {"type": "string"}}),
    ("super_memory_consolidate", "Record a safe non-destructive consolidation event.", {"strategy": {"type": "string", "default": "all"}, "dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}),
    ("super_memory_gaps", "Detect/record a knowledge gap event.", {"topic": {"type": "string"}, "action": {"type": "string", "default": "detect"}, "config_path": {"type": "string"}}),
    ("super_memory_explain", "Explain relationship by merged recall path.", {"from_entity": {"type": "string"}, "to_entity": {"type": "string"}, "config_path": {"type": "string"}}),
    ("super_memory_situation", "Return current memory situation summary.", {"config_path": {"type": "string"}}),
    ("super_memory_reflex", "Record reflex pin/unpin intent for a memory.", {"memory_id": {"type": "string"}, "action": {"type": "string", "default": "pin"}, "config_path": {"type": "string"}}),
    ("super_memory_boundaries", "List or save domain boundary memory.", {"domain": {"type": "string", "default": "global"}, "content": {"type": "string"}, "config_path": {"type": "string"}}),
]:
    TOOLS[_name] = {"description": _desc, "inputSchema": _schema(_props)}

for _name in ["train", "import", "index", "sync", "telegram_backup", "visualize", "store", "watch"]:
    TOOLS[f"super_memory_{_name}"] = {
        "description": f"Phase 4 optional/heavy {_name} skeleton; disabled unless explicitly configured.",
        "inputSchema": _schema({"params": {"type": "object"}}),
    }

for _name, _desc, _props in [
    ("super_memory_working_memory_get", "Get Phase 6 short-lived working memory state.", {"key": {"type": "string", "default": "default"}, "config_path": {"type": "string"}}),
    ("super_memory_working_memory_set", "Set/merge Phase 6 short-lived working memory state.", {"key": {"type": "string", "default": "default"}, "payload": {"type": "object"}, "ttl_seconds": {"type": "integer"}, "config_path": {"type": "string"}}),
    ("super_memory_attention_score", "Score memory salience and routing signals.", {"payload": {"type": "object"}, "config_path": {"type": "string"}}),
    ("super_memory_route_memory", "Route a memory payload using deterministic Phase 6 attention policy.", {"payload": {"type": "object"}, "config_path": {"type": "string"}}),
    ("super_memory_parallel_save", "Run Phase 6 working-memory plus canonical-first save/projection flow.", {"payload": {"type": "object"}, "config_path": {"type": "string"}}),
    ("super_memory_recall_arbitrate", "Recall from layers and explain layer arbitration.", {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}, "config_path": {"type": "string"}}),
    ("super_memory_consolidation_cycle", "Run a bounded deterministic Phase 6 consolidation report.", {"strategy": {"type": "string", "default": "light"}, "dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}),
    ("super_memory_conflict_resolve", "Record a Phase 6 conflict resolution event.", {"conflict_id": {"type": "string"}, "resolution": {"type": "string"}, "reason": {"type": "string"}, "config_path": {"type": "string"}}),
    ("super_memory_promotion_candidates", "List deterministic promotion candidates.", {"limit": {"type": "integer", "default": 20}, "config_path": {"type": "string"}}),
    ("super_memory_feedback_outcome", "Record task/memory outcome feedback for learning.", {"memory_id": {"type": "string"}, "success": {"type": "boolean", "default": True}, "outcome": {"type": "string"}, "config_path": {"type": "string"}}),
]:
    TOOLS[_name] = {"description": _desc, "inputSchema": _schema(_props, [k for k in ["payload", "query", "conflict_id", "resolution"] if k in _props])}


for _name, _desc, _props, _required in [
    ("super_memory_graph_stats", "Show Layer 4 neuron/synapse/fiber counts.", {"config_path": {"type": "string"}}, []),
    ("super_memory_graph_neighbors", "List graph neighbors for a neuron or memory id.", {"id": {"type": "string"}, "direction": {"type": "string", "default": "out"}, "limit": {"type": "integer", "default": 20}, "config_path": {"type": "string"}}, ["id"]),
    ("super_memory_graph_recall", "Recall cognitive fibers from Layer 4 graph.", {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}, "config_path": {"type": "string"}}, ["query"]),
    ("super_memory_spreading_activation_recall", "Neural-memory-style spreading activation recall through the cognitive graph.", {"query": {"type": "string"}, "depth": {"type": "integer", "default": 2}, "top_k": {"type": "integer", "default": 20}, "seed_limit": {"type": "integer", "default": 30}, "config_path": {"type": "string"}}, ["query"]),
    ("nmem_recall", "Compatibility alias: neural-memory-style spreading activation recall.", {"query": {"type": "string"}, "depth": {"type": "integer", "default": 2}, "top_k": {"type": "integer", "default": 20}, "seed_limit": {"type": "integer", "default": 30}, "config_path": {"type": "string"}}, ["query"]),
    ("super_memory_graph_rebuild", "Rebuild derived Layer 4 graph from SQLite memories.", {"limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_graph_cleanup_orphans", "Delete orphan graph neurons/synapses/fibers pointing to soft-deleted/missing memories.", {"config_path": {"type": "string"}}, []),
    ("super_memory_dedup_neurons", "Merge duplicate cognitive neurons (same content_hash), rewiring synapses to the kept neuron.", {"dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, []),
    ("super_memory_hypothesis_create", "Create a deterministic cognitive hypothesis.", {"content": {"type": "string"}, "confidence": {"type": "number", "default": 0.5}, "tags": {"type": "array", "items": {"type": "string"}}, "config_path": {"type": "string"}}, ["content"]),
    ("super_memory_hypothesis_get", "Get hypothesis detail with evidence/predictions.", {"hypothesis_id": {"type": "string"}, "config_path": {"type": "string"}}, ["hypothesis_id"]),
    ("super_memory_hypothesis_list", "List hypotheses.", {"status": {"type": "string"}, "limit": {"type": "integer", "default": 20}, "config_path": {"type": "string"}}, []),
    ("super_memory_evidence_add", "Add evidence for/against a hypothesis.", {"hypothesis_id": {"type": "string"}, "content": {"type": "string"}, "direction": {"type": "string", "default": "for"}, "weight": {"type": "number", "default": 0.5}, "config_path": {"type": "string"}}, ["hypothesis_id", "content"]),
    ("super_memory_prediction_create", "Create a falsifiable prediction.", {"content": {"type": "string"}, "confidence": {"type": "number", "default": 0.7}, "hypothesis_id": {"type": "string"}, "deadline": {"type": "string"}, "config_path": {"type": "string"}}, ["content"]),
    ("super_memory_prediction_list", "List predictions.", {"status": {"type": "string"}, "limit": {"type": "integer", "default": 20}, "config_path": {"type": "string"}}, []),
    ("super_memory_verify_prediction", "Verify a prediction as correct/wrong.", {"prediction_id": {"type": "string"}, "outcome": {"type": "string"}, "content": {"type": "string"}, "config_path": {"type": "string"}}, ["prediction_id", "outcome"]),
    ("super_memory_lifecycle_review", "Review lifecycle hygiene.", {"limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_lifecycle_cache", "Manage local activation cache status/save/load/clear.", {"action": {"type": "string", "default": "status"}, "config_path": {"type": "string"}}, []),
    ("super_memory_lifecycle_tier", "Evaluate/apply deterministic memory tiers.", {"action": {"type": "string", "default": "evaluate"}, "dry_run": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_lifecycle_compression", "Review/mark compression candidates without truncating content.", {"action": {"type": "string", "default": "review"}, "dry_run": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_leitner", "Leitner 5-box: queue|mark|schedule|stats|auto_seed.", {"action": {"type": "string", "default": "queue"}, "memory_id": {"type": "string"}, "success": {"type": "boolean", "default": True}, "box": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 50}, "config_path": {"type": "string"}}, []),
    ("super_memory_reflex_status", "Show reflex audit events and missing refs.", {"config_path": {"type": "string"}}, []),
    ("super_memory_train_local", "Train from local text/rich docs under workspace only.", {"path": {"type": "string"}, "domain_tag": {"type": "string", "default": "local"}, "recursive": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 200}, "save": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, ["path"]),
    ("super_memory_index_local", "Index code symbols/imports under workspace only.", {"path": {"type": "string"}, "extensions": {"type": "array", "items": {"type": "string"}}, "recursive": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 500}, "save": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, ["path"]),
    ("super_memory_index_status", "Show local code index manifest status.", {"config_path": {"type": "string"}}, []),
    ("super_memory_import_local", "Import local markdown/text/json/jsonl under workspace only.", {"path": {"type": "string"}, "source_name": {"type": "string", "default": "local-import"}, "recursive": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 200}, "save": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, ["path"]),
    ("super_memory_watch_scan", "One-shot file watch scan; no daemon.", {"directory": {"type": "string"}, "recursive": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 200}, "save": {"type": "boolean", "default": False}, "config_path": {"type": "string"}}, ["directory"]),
    ("super_memory_sync_status", "Show sync status only; cloud disabled.", {"config_path": {"type": "string"}}, []),
    ("super_memory_store_status", "Show store status only; community store disabled.", {"config_path": {"type": "string"}}, []),
]:
    TOOLS[_name] = {"description": _desc, "inputSchema": _schema(_props, _required)}


for _name, _desc, _props, _required in [
    ("super_memory_forget", "Delete a memory. Soft delete by default. Hard delete cascades to graph and projections.", {"memory_id": {"type": "string"}, "hard": {"type": "boolean", "default": False}, "reason": {"type": "string", "default": ""}, "config_path": {"type": "string"}}, ["memory_id"]),
    ("super_memory_edit", "Edit a memory's content, type, priority, or tier. Preserves all synapses.", {"memory_id": {"type": "string"}, "content": {"type": "string"}, "type": {"type": "string"}, "priority": {"type": "integer"}, "tier": {"type": "string"}, "config_path": {"type": "string"}}, ["memory_id"]),
    ("super_memory_dream_insight_generation", "Dream Phase 1: Generate synthetic insight memories from cross-domain bridges.", {"limit": {"type": "integer", "default": 200}, "dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, []),
    ("super_memory_dream_weak_tie_reinforcement", "Dream Phase 2: Strengthen weak graph synapses.", {"limit": {"type": "integer", "default": 200}, "dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, []),
    ("super_memory_dream_pattern_summary", "Dream Phase 3: Generate pattern-summary memories from repetitive content.", {"limit": {"type": "integer", "default": 200}, "dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, []),
    ("super_memory_dream_full_cycle", "Run full Dream Engine cycle (insight -> weak tie -> pattern).", {"limit": {"type": "integer", "default": 200}, "dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, []),
    ("super_memory_telemetry_record_event", "Record a telemetry event for usage tracking.", {"kind": {"type": "string"}, "agent_id": {"type": "string", "default": "lucas"}, "tool_name": {"type": "string"}, "duration_ms": {"type": "number"}, "success": {"type": "boolean", "default": True}, "detail": {"type": "object"}, "config_path": {"type": "string"}}, ["kind"]),
    ("super_memory_telemetry_stats", "Get telemetry usage statistics for recent days.", {"days": {"type": "integer", "default": 7}, "config_path": {"type": "string"}}, []),
    ("super_memory_telemetry_aggregate_daily", "Aggregate today's telemetry into daily rollup.", {"config_path": {"type": "string"}}, []),
    ("super_memory_isolation_set_rules", "Set per-agent isolation rules for memory scoping.", {"agent_id": {"type": "string"}, "allowed_scopes": {"type": "array", "items": {"type": "string"}}, "allowed_agents": {"type": "array", "items": {"type": "string"}}, "blocked_agents": {"type": "array", "items": {"type": "string"}}, "read_others": {"type": "boolean"}, "config_path": {"type": "string"}}, ["agent_id"]),
    ("super_memory_isolation_get_rules", "Get isolation rules for a specific agent.", {"agent_id": {"type": "string"}, "config_path": {"type": "string"}}, ["agent_id"]),
    ("super_memory_isolation_summary", "Summary of all agent isolation rules.", {"config_path": {"type": "string"}}, []),
    ("super_memory_isolation_agent_counts", "Count memories per agent scope.", {"config_path": {"type": "string"}}, []),
    ("super_memory_autocomplete_suggest", "Suggest memory completions from prefix index.", {"prefix": {"type": "string"}, "limit": {"type": "integer", "default": 5}, "type_filter": {"type": "string"}, "config_path": {"type": "string"}}, ["prefix"]),
    ("super_memory_autocomplete_idle", "Find idle/neglected memories needing reinforcement.", {"config_path": {"type": "string"}}, []),
    ("super_memory_autocomplete_rebuild", "Rebuild full autocomplete prefix index.", {"config_path": {"type": "string"}}, []),
    ("super_memory_autocomplete_status", "Show autocomplete prefix index status.", {"config_path": {"type": "string"}}, []),
    ("super_memory_recommendations", "Recommend ranked next actions for Super Memory maintenance and UX.", {"limit": {"type": "integer", "default": 10}, "config_path": {"type": "string"}}, []),
    ("super_memory_deep_audit", "Comprehensive memory health audit.", {"config_path": {"type": "string"}}, []),
    ("super_memory_deep_qualify", "Score memory quality and recall pipeline.", {"config_path": {"type": "string"}}, []),
    ("super_memory_deep_debug", "Find operational issues and misconfigurations.", {"config_path": {"type": "string"}}, []),
    ("super_memory_deep_improve", "Generate and optionally apply improvement proposals.", {"dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}, "async_mode": {"type": "boolean", "default": True}, "compact": {"type": "boolean", "default": True}, "max_seconds": {"type": "integer", "default": 3}}, []),
    ("super_memory_auto_deep_pipeline", "Run full Auto Deep pipeline: Audit -> Qualify -> Debug -> Improve.", {"dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, []),
    ("super_memory_capture_failed_recall", "Capture a failed recall/correction into self-training queue and recall regression case.", {"query": {"type": "string"}, "wrong_answer": {"type": "string"}, "expected_answer": {"type": "string"}, "notes": {"type": "string"}, "config_path": {"type": "string"}}, ["query"]),
    ("super_memory_project_state_update", "Append a structured project-state update to canonical project memory markdown.", {"project": {"type": "string"}, "summary": {"type": "string"}, "facts": {"type": "object"}, "config_path": {"type": "string"}}, []),
    ("super_memory_issue_memory_update", "Write/update a canonical issue memory markdown file.", {"title": {"type": "string"}, "status": {"type": "string"}, "cause": {"type": "string"}, "fix": {"type": "string"}, "verification": {"type": "string"}, "config_path": {"type": "string"}}, ["title"]),
    # P0: MemoryEnvelope
    ("super_memory_build_envelope", "Build a MemoryEnvelope v1 with quality/trust/provenance/lifecycle metadata.", {"content": {"type": "string"}, "memory_type": {"type": "string"}, "scope": {"type": "string"}, "agent_id": {"type": "string", "default": "lucas"}, "session_id": {"type": "string"}, "project": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "source_adapter": {"type": "string", "default": "direct"}, "trust_score": {"type": "number"}, "lifecycle_tier": {"type": "string", "default": "warm"}, "auto_pin": {"type": "boolean", "default": False}, "config_path": {"type": "string"}}, ["content"]),
    ("super_memory_remember_through_envelope", "Build envelope + save through canonical bridge.remember().", {"content": {"type": "string"}, "memory_type": {"type": "string"}, "scope": {"type": "string"}, "agent_id": {"type": "string", "default": "lucas"}, "session_id": {"type": "string"}, "project": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "source_adapter": {"type": "string", "default": "direct"}, "trust_score": {"type": "number"}, "lifecycle_tier": {"type": "string", "default": "warm"}, "auto_pin": {"type": "boolean", "default": False}, "config_path": {"type": "string"}}, ["content"]),
    # P0: SourceAdapter
    ("super_memory_ingest_through_adapter", "Ingest a source through the best matching SourceAdapter (chat/file/url).", {"source_path": {"type": "string"}, "agent_id": {"type": "string", "default": "lucas"}, "session_id": {"type": "string"}, "project": {"type": "string"}, "config_path": {"type": "string"}}, ["source_path"]),
    ("super_memory_list_source_adapters", "List all registered SourceAdapters with versions and transformations.", {"config_path": {"type": "string"}}, []),
    ("super_memory_ingest_and_remember", "Ingest through adapter + save all payloads via canonical bridge.", {"source_path": {"type": "string"}, "agent_id": {"type": "string", "default": "lucas"}, "session_id": {"type": "string"}, "project": {"type": "string"}, "config_path": {"type": "string"}}, ["source_path"]),
    # P0: Semantic Closets/Drawers
    ("super_memory_build_closets", "Build semantic closet/drawer entries for one memory.", {"memory_id": {"type": "string"}, "config_path": {"type": "string"}}, ["memory_id"]),
    ("super_memory_rebuild_all_closets", "Rebuild closets for all active workspace_markdown memories.", {"limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_search_closets", "Search semantic closets by keyword.", {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}, "config_path": {"type": "string"}}, ["query"]),
    ("super_memory_hydrate_drawers", "Hydrate verbatim content from closet/drawer references with neighbor expansion.", {"drawer_ids": {"type": "array", "items": {"type": "string"}}, "closet_ids": {"type": "array", "items": {"type": "string"}}, "config_path": {"type": "string"}}, []),
    ("super_memory_closet_stats", "Get closet/drawer statistics.", {"config_path": {"type": "string"}}, []),
    # P0: Recall Arbitration v3
    ("super_memory_recall_arbitrate_v3", "Unified recall arbitration v3 with explanations, layer votes, and citations.", {"query": {"type": "string"}, "limit": {"type": "integer", "default": 10}, "config_path": {"type": "string"}, "min_score": {"type": "number", "default": 0.0}}, ["query"]),
    ("super_memory_recall_quick", "Lightweight quick search (lexical only, no graph).", {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}, "config_path": {"type": "string"}}, ["query"]),
    # P0: Recall Feedback Loop
    ("super_memory_recall_record_event", "Record a recall event for feedback tracking.", {"query": {"type": "string"}, "selected_memory_ids": {"type": "array", "items": {"type": "string"}}, "shown_to_user": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, ["query", "selected_memory_ids"]),
    ("super_memory_recall_record_feedback", "Record outcome feedback for a recall event (used/ignored/corrected/contradicted/missed).", {"recall_event_id": {"type": "string"}, "memory_id": {"type": "string"}, "outcome": {"type": "string"}, "confidence": {"type": "number", "default": 1.0}, "notes": {"type": "string"}, "config_path": {"type": "string"}}, ["recall_event_id", "memory_id", "outcome"]),
    ("super_memory_recall_record_correction", "Record a correction + generate training case.", {"query": {"type": "string"}, "memory_id": {"type": "string"}, "wrong_answer": {"type": "string"}, "expected_answer": {"type": "string"}, "notes": {"type": "string"}, "config_path": {"type": "string"}}, ["query"]),
    ("super_memory_recall_feedback_stats", "Get recall feedback statistics (success/correction rates).", {"config_path": {"type": "string"}}, []),
    ("super_memory_recall_generate_training_cases", "Generate benchmark training cases from corrected recall events.", {"min_corrections": {"type": "integer", "default": 3}, "config_path": {"type": "string"}}, []),
    ("super_memory_recall_benchmark_seed", "Seed default recall benchmark cases for release gating.", {"overwrite": {"type": "boolean", "default": False}, "config_path": {"type": "string"}}, []),
    ("super_memory_recall_release_gate", "Run release-gating recall benchmark check.", {"limit": {"type": "integer", "default": 100}, "config_path": {"type": "string"}}, []),
    ("super_memory_scheduled_maintenance_report", "Run daily/weekly/release maintenance profile.", {"profile": {"type": "string", "default": "daily"}, "dry_run": {"type": "boolean", "default": False}, "config_path": {"type": "string"}}, []),
    # P2: Projection Drift Repair
    ("super_memory_audit_drift", "Audit drift across all derived projections (orphaned, stale, missing).", {"config_path": {"type": "string"}}, []),
    ("super_memory_repair_orphans", "Repair orphaned projection entries.", {"dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, []),
    ("super_memory_full_drift_repair", "Full drift repair: audit + orphans + missing closets.", {"dry_run": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, []),
    ("super_memory_register_projection", "Register a derived projection for drift tracking.", {"table_name": {"type": "string"}, "memory_id": {"type": "string"}, "projection_key": {"type": "string"}, "config_path": {"type": "string"}}, ["table_name", "memory_id", "projection_key"]),
    # P2: Adapter-driven Watcher
    ("super_memory_adapter_scan_once", "One-shot scan using SourceAdapters (detect changes + ingest through adapters).", {"directories": {"type": "array", "items": {"type": "string"}}, "exclude": {"type": "array", "items": {"type": "string"}}, "config_path": {"type": "string"}}, []),
    ("super_memory_adapter_settle_scan", "Debounced adapter-driven scan with settle detection.", {"directories": {"type": "array", "items": {"type": "string"}}, "exclude": {"type": "array", "items": {"type": "string"}}, "config_path": {"type": "string"}}, []),
    ("super_memory_adapter_monitor_status", "Get adapter monitor status.", {"config_path": {"type": "string"}}, []),
    # P2: Line Citations
    ("super_memory_enrich_recall_with_citations", "Build enriched citations from a recall result with line numbers and neighbor context.", {"recall_result": {"type": "object"}, "neighbor_lines": {"type": "integer", "default": 3}, "config_path": {"type": "string"}}, ["recall_result"]),
    ("super_memory_track_source", "Register source file tracking for a memory.", {"memory_id": {"type": "string"}, "file_path": {"type": "string"}, "line_start": {"type": "integer", "default": 0}, "config_path": {"type": "string"}}, ["memory_id", "file_path"]),
    # P2: Agentic Dialectic Mode
    ("super_memory_dialectic_answer", "Answer using optional dialectic reasoning (format or synthesize).", {"query": {"type": "string"}, "recall_result": {"type": "object"}, "mode": {"type": "string", "default": "format"}, "config_path": {"type": "string"}}, ["query"]),
    # P2: Self-Education Curriculum
    ("super_memory_analyze_recall_failures", "Analyze recall feedback for failure patterns.", {"config_path": {"type": "string"}}, []),
    ("super_memory_generate_curriculum", "Full curriculum pipeline: analyze -> generate cases -> generate tests.", {"config_path": {"type": "string"}}, []),
    ("super_memory_run_benchmark_tests", "Run benchmark tests against training cases.", {"config_path": {"type": "string"}}, []),
]:
    TOOLS[_name] = {"description": _desc, "inputSchema": _schema(_props, _required)}

def _allowed_tools(profile: str | None = None) -> set[str]:
    effective = (profile or MCP_PROFILE or "normal").lower()
    if effective == "admin":
        return ADMIN_TOOLS
    if effective == "curated":
        # Curated names are a subset of ADMIN; intersect with TOOLS so any
        # name drift never exposes a missing tool descriptor.
        return CURATED_TOOLS & set(TOOLS)
    if effective == "all":
        return set(TOOLS)
    return NORMAL_TOOLS


def _tool_descriptors(profile: str | None = None) -> list[JSON]:
    allowed = _allowed_tools(profile)
    return [{"name": name, **meta} for name, meta in TOOLS.items() if name in allowed]


def _call_tool(name: str, args: JSON) -> Any:
    if name not in _allowed_tools():
        raise PermissionError(f"tool not exposed in {MCP_PROFILE!r} MCP profile: {name}")
    if name == "super_memory_remember":
        config_path = args.pop("config_path", None)
        return bridge.remember(args, config_path=config_path)
    if name == "super_memory_remember_batch":
        config_path = args.pop("config_path", None)
        return bridge.remember_batch(args["memories"], config_path=config_path)
    if name == "super_memory_show":
        return bridge.show(args["memory_id"], config_path=args.get("config_path"))
    if name == "super_memory_context":
        return bridge.context(args.get("query", ""), limit=args.get("limit", 10), config_path=args.get("config_path"))
    if name == "super_memory_todo":
        return bridge.todo(args["task"], priority=args.get("priority", 5), config_path=args.get("config_path"))
    if name == "super_memory_auto":
        return bridge.auto(args["text"], save=args.get("save", False), config_path=args.get("config_path"))
    if name == "super_memory_stats":
        return bridge.stats(config_path=args.get("config_path"))
    if name == "super_memory_diagnostics":
        return bridge.diagnostics(config_path=args.get("config_path"))
    if name == "super_memory_memory_slot_contract":
        return bridge.memory_slot_contract(config_path=args.get("config_path"))
    if name == "super_memory_mcp_contract":
        return bridge.mcp_contract(profile=args.get("profile", "admin"), config_path=args.get("config_path"))
    if name == "super_memory_supervised_runtime_smoke":
        return bridge.supervised_runtime_smoke(config_path=args.get("config_path"))
    if name == "super_memory_health":
        return bridge.health(config_path=args.get("config_path"))
    if name == "super_memory_cross_layer_health":
        return bridge.cross_layer_health(config_path=args.get("config_path"), parity_threshold=args.get("parity_threshold", 10))
    if name == "super_memory_sanitize_prompt":
        return {"text": bridge.sanitize_prompt(args["text"])}
    if name == "super_memory_sanitize_auto_capture":
        return {"text": bridge.sanitize_auto_capture(args["text"])}
    if name == "super_memory_normalize_memory":
        return bridge.normalize_memory_payload(args["memory"], auto_capture=args.get("auto_capture", False))
    if name == "super_memory_recall":
        return bridge.recall(args["query"], limit=args.get("limit", 10), config_path=args.get("config_path"))
    if name == "super_memory_prefetch":
        return bridge.prefetch(args["query"], limit=args.get("limit", 10), config_path=args.get("config_path"))
    if name == "super_memory_sync_turn":
        config_path = args.pop("config_path", None)
        return bridge.sync_turn(args, config_path=config_path)
    if name == "super_memory_memory_search":
        return bridge.memory_search(
            args["query"],
            max_results=args.get("max_results", 5),
            min_score=args.get("min_score", 0.0),
            corpus=args.get("corpus", "all"),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_memory_get":
        return bridge.memory_get(
            args["path"],
            from_line=args.get("from_line", 1),
            lines=args.get("lines", 20),
            corpus=args.get("corpus", "all"),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_promote":
        return bridge.promote(args["memory_id"], config_path=args.get("config_path"))
    if name == "super_memory_status":
        return bridge.status(config_path=args.get("config_path"))
    if name == "super_memory_index_sessions":
        return bridge.index_sessions(config_path=args.get("config_path"))
    if name == "super_memory_session_index_status":
        return bridge.session_index_status(config_path=args.get("config_path"))
    if name == "super_memory_search_sessions":
        return bridge.search_sessions(
            args["query"],
            max_results=args.get("max_results", 5),
            min_score=args.get("min_score", 0.0),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_cooldown_status":
        return bridge.cooldown_status(config_path=args.get("config_path"))
    if name == "super_memory_cooldown_clear":
        return bridge.cooldown_clear(config_path=args.get("config_path"))
    # P1 Search Quality
    if name == "super_memory_hybrid_fuse":
        return bridge.hybrid_fuse(
            args["text_results"], args["vector_results"],
            text_weight=args.get("text_weight", 0.5),
            vector_weight=args.get("vector_weight", 0.5),
            top_k=args.get("top_k"),
        )
    if name == "super_memory_diversify_results":
        return bridge.diversify_results(
            args["results"], args["query"],
            top_k=args.get("top_k"),
            lambda_param=args.get("lambda_param", 0.7),
        )
    if name == "super_memory_temporal_decay":
        return bridge.apply_temporal_decay(
            args["results"],
            corpus=args.get("corpus", "memory"),
            half_life=args.get("half_life"),
        )
    if name == "super_memory_session_boost":
        return bridge.boost_current_session(
            args["results"],
            current_session_id=args.get("current_session_id"),
            boost_factor=args.get("boost_factor", 0.3),
        )
    # P2 Embedding Providers
    if name == "super_memory_list_embedding_providers":
        return bridge.list_embedding_providers(config_path=args.get("config_path"))
    if name == "super_memory_embed_text":
        return bridge.embed_text(
            args["text"],
            dimensions=args.get("dimensions"),
            config_path=args.get("config_path"),
        )
    # P3 Infrastructure
    if name == "super_memory_rem_search":
        return bridge.rem_search(
            args["query_vector"],
            top_k=args.get("top_k", 10),
            min_score=args.get("min_score", 0.0),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_rem_health":
        return bridge.rem_health(config_path=args.get("config_path"))
    if name == "super_memory_watcher_scan":
        return bridge.watcher_scan(
            directories=args.get("directories"),
            exclude=args.get("exclude"),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_flush_plan_status":
        return bridge.flush_plan_status(config_path=args.get("config_path"))
    if name == "super_memory_flush_session_memories":
        return bridge.flush_session_memories(
            limit=args.get("limit", 100),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_reindex_all":
        return bridge.reindex_all(config_path=args.get("config_path"))
    if name == "super_memory_get_index_identity":
        return bridge.get_index_identity(config_path=args.get("config_path"))
    if name == "super_memory_set_index_identity":
        return bridge.set_index_identity(
            args["provider_id"],
            model=args.get("model", ""),
            dimensions=args.get("dimensions", 384),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_self_heal_embeddings":
        return bridge.self_heal_embeddings(
            batch_size=args.get("batch_size", 50),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_self_heal_status":
        return bridge.self_heal_status(config_path=args.get("config_path"), mode=args.get("mode", "fast"))
    if name == "super_memory_write_contract_process_jobs":
        return bridge.write_contract_process_jobs(limit=args.get("limit", 50), config_path=args.get("config_path"))
    if name == "super_memory_write_contract_reconcile":
        return bridge.write_contract_reconcile(limit=args.get("limit", 200), config_path=args.get("config_path"))
    if name == "super_memory_write_contract_semantic_merge":
        return bridge.write_contract_semantic_merge(threshold=args.get("threshold", 0.92), simhash_distance=args.get("simhash_distance", 3), limit=args.get("limit", 500), dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_duplicate_resolution_v2":
        return bridge.duplicate_resolution_v2(threshold=args.get("threshold", 0.92), simhash_distance=args.get("simhash_distance", 3), limit=args.get("limit", 500), dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_self_improvement_orchestrator":
        return bridge.self_improvement_orchestrator(dry_run=args.get("dry_run", True), limit=args.get("limit", 500), remember_lesson=args.get("remember_lesson", True), config_path=args.get("config_path"))
    if name == "super_memory_project_backfill":
        return bridge.project_backfill(limit=args.get("limit", 2000), dry_run=args.get("dry_run", True), rebuild_graph=args.get("rebuild_graph", False), config_path=args.get("config_path"))
    if name == "super_memory_project_synapse_backfill":
        return bridge.project_synapse_backfill(limit=args.get("limit", 2000), dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_maintenance_enqueue":
        return bridge.maintenance_enqueue(args["job_type"], args=args.get("args") or {}, config_path=args.get("config_path"))
    if name == "super_memory_maintenance_job_status":
        return bridge.maintenance_job_status(args["job_id"], config_path=args.get("config_path"))
    if name == "super_memory_maintenance_process_jobs":
        return bridge.maintenance_process_jobs(limit=args.get("limit", 5), config_path=args.get("config_path"))
    if name == "super_memory_build_prompt_section":
        return bridge.build_prompt_section(
            args["results"],
            title=args.get("title", "Memory Context"),
            max_tokens=args.get("max_tokens", 4000),
            include_citations=args.get("include_citations", True),
        )
    if name == "super_memory_generate_narrative":
        return bridge.generate_narrative(
            title=args.get("title", "Dreaming Narrative"),
            out_dir=args.get("out_dir"),
            max_insights=args.get("max_insights", 10),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_rem_extract_all":
        return bridge.rem_extract_all(
            min_confidence=args.get("min_confidence", 0.6),
            promote=args.get("promote", True),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_qmd_search":
        return bridge.qmd_search(args["query"], limit=args.get("limit", 10))
    if name == "super_memory_qmd_health":
        return bridge.qmd_health()
    if name == "super_memory_qmd_start":
        return bridge.qmd_start()
    if name == "super_memory_qmd_stop":
        return bridge.qmd_stop()
    if name == "super_memory_watcher_settle_scan":
        return bridge.watcher_settle_scan(
            directories=args.get("directories"),
            exclude=args.get("exclude"),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_batch_state_status":
        return bridge.batch_state_status()
    if name == "super_memory_reset_batch_state":
        return bridge.reset_batch_state()
    if name == "super_memory_reindex_fsm_status":
        return bridge.reindex_fsm_status()
    if name == "super_memory_reindex_fts_only":
        return bridge.reindex_fts_only(config_path=args.get("config_path"))
    if name == "super_memory_sync_interval_status":
        return bridge.sync_interval_status()
    if name == "super_memory_sync_interval_start":
        return bridge.sync_interval_start()
    if name == "super_memory_sync_interval_stop":
        return bridge.sync_interval_stop()
    if name == "super_memory_sync_startup_catchup":
        return bridge.sync_startup_catchup()
    if name == "super_memory_recovery_status":
        return bridge.recovery_status(db_path=args.get("db_path"))
    if name == "super_memory_reset_recovery_state":
        return bridge.reset_recovery_state(db_path=args.get("db_path"))
    if name == "super_memory_conflicts":
        return bridge.conflicts(content=args.get("content"), memory_id=args.get("memory_id"), config_path=args.get("config_path"))
    if name == "super_memory_provenance":
        return bridge.provenance(args["memory_id"], action=args.get("action", "trace"), actor=args.get("actor", "super-memory"), config_path=args.get("config_path"))
    if name == "super_memory_source":
        config_path = args.pop("config_path", None)
        return bridge.source(args, config_path=config_path)
    if name == "super_memory_version":
        config_path = args.pop("config_path", None)
        action = args.pop("action", "create")
        name_arg = args.pop("name", "snapshot")
        return bridge.version(action=action, name=name_arg, config_path=config_path, **args)
    if name == "super_memory_pin":
        return bridge.pin(args["memory_id"], action=args.get("action", "pin"), config_path=args.get("config_path"))
    if name == "super_memory_consolidate":
        return bridge.consolidate(strategy=args.get("strategy", "all"), dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_gaps":
        return bridge.gaps(args["topic"], action=args.get("action", "detect"), config_path=args.get("config_path"))
    if name == "super_memory_explain":
        return bridge.explain(args["from_entity"], args["to_entity"], config_path=args.get("config_path"))
    if name == "super_memory_situation":
        return bridge.situation(config_path=args.get("config_path"))
    if name == "super_memory_reflex":
        return bridge.reflex(args["memory_id"], action=args.get("action", "pin"), config_path=args.get("config_path"))
    if name == "super_memory_boundaries":
        return bridge.boundaries(domain=args.get("domain", "global"), content=args.get("content"), config_path=args.get("config_path"))
    if name.startswith("super_memory_") and name.replace("super_memory_", "") in {"train", "import", "index", "sync", "telegram_backup", "visualize", "store", "watch"}:
        return bridge.optional_heavy(name.replace("super_memory_", ""), **(args.get("params") or {}))
    if name == "super_memory_working_memory_get":
        return bridge.working_memory_get(key=args.get("key", "default"), config_path=args.get("config_path"))
    if name == "super_memory_working_memory_set":
        return bridge.working_memory_set(args.get("payload", {}), key=args.get("key", "default"), ttl_seconds=args.get("ttl_seconds"), config_path=args.get("config_path"))
    if name == "super_memory_attention_score":
        return bridge.attention_score(args["payload"], config_path=args.get("config_path"))
    if name == "super_memory_route_memory":
        return bridge.route_memory(args["payload"], config_path=args.get("config_path"))
    if name == "super_memory_parallel_save":
        return bridge.parallel_save(args["payload"], config_path=args.get("config_path"))
    if name == "super_memory_recall_arbitrate":
        return bridge.recall_arbitrate(args["query"], limit=args.get("limit", 10), config_path=args.get("config_path"))
    if name == "super_memory_consolidation_cycle":
        return bridge.consolidation_cycle(strategy=args.get("strategy", "light"), dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_conflict_resolve":
        return bridge.conflict_resolve(args["conflict_id"], args["resolution"], reason=args.get("reason", ""), config_path=args.get("config_path"))
    if name == "super_memory_promotion_candidates":
        return bridge.promotion_candidates(limit=args.get("limit", 20), config_path=args.get("config_path"))
    if name == "super_memory_feedback_outcome":
        return bridge.feedback_outcome(memory_id=args.get("memory_id"), success=args.get("success", True), outcome=args.get("outcome", ""), config_path=args.get("config_path"))

    if name == "super_memory_graph_stats":
        return bridge.graph_stats(config_path=args.get("config_path"))
    if name == "super_memory_graph_neighbors":
        return bridge.graph_neighbors(args["id"], direction=args.get("direction", "out"), limit=args.get("limit", 20), config_path=args.get("config_path"))
    if name == "super_memory_graph_recall":
        return bridge.graph_recall(args["query"], limit=args.get("limit", 10), config_path=args.get("config_path"))
    if name == "super_memory_spreading_activation_recall":
        return bridge.spreading_activation_recall(args["query"], depth=args.get("depth", 2), top_k=args.get("top_k", 20), seed_limit=args.get("seed_limit", 30), config_path=args.get("config_path"))
    if name == "nmem_recall":
        result = bridge.spreading_activation_recall(args["query"], depth=args.get("depth", 2), top_k=args.get("top_k", 20), seed_limit=args.get("seed_limit", 30), config_path=args.get("config_path"))
        return {"answer": result.get("results", []), "confidence": 1.0 if result.get("results") else 0.0, "neurons_activated": result.get("total_activated", 0), "depth_used": result.get("depth", args.get("depth", 2)), "elapsed_ms": result.get("elapsed_ms", 0), "raw": result}
    if name == "super_memory_graph_rebuild":
        return bridge.graph_rebuild(limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_graph_cleanup_orphans":
        from . import graph as _graph
        return _graph.cleanup_orphans(config_path=args.get("config_path"))
    if name == "super_memory_dedup_neurons":
        from . import stabilize as _stabilize
        from .storage import SuperMemoryStore as _Store
        from .config import load_config as _load_config
        _store = _Store(_load_config(args.get("config_path")))
        return _stabilize.dedup_neurons(_store, dry_run=args.get("dry_run", True))
    if name == "super_memory_hypothesis_create":
        return bridge.hypothesis_create(args["content"], confidence=args.get("confidence", 0.5), tags=args.get("tags") or [], config_path=args.get("config_path"))
    if name == "super_memory_hypothesis_get":
        return bridge.hypothesis_get(args["hypothesis_id"], config_path=args.get("config_path"))
    if name == "super_memory_hypothesis_list":
        return bridge.hypothesis_list(status=args.get("status"), limit=args.get("limit", 20), config_path=args.get("config_path"))
    if name == "super_memory_evidence_add":
        return bridge.evidence_add(args["hypothesis_id"], args["content"], direction=args.get("direction", "for"), weight=args.get("weight", 0.5), config_path=args.get("config_path"))
    if name == "super_memory_prediction_create":
        return bridge.prediction_create(args["content"], confidence=args.get("confidence", 0.7), hypothesis_id=args.get("hypothesis_id"), deadline=args.get("deadline"), config_path=args.get("config_path"))
    if name == "super_memory_prediction_list":
        return bridge.prediction_list(status=args.get("status"), limit=args.get("limit", 20), config_path=args.get("config_path"))
    if name == "super_memory_verify_prediction":
        return bridge.verify_prediction(args["prediction_id"], args["outcome"], content=args.get("content", ""), config_path=args.get("config_path"))
    if name == "super_memory_lifecycle_review":
        return bridge.lifecycle_review(limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_lifecycle_cache":
        return bridge.lifecycle_cache(action=args.get("action", "status"), config_path=args.get("config_path"))
    if name == "super_memory_lifecycle_tier":
        return bridge.lifecycle_tier(action=args.get("action", "evaluate"), dry_run=args.get("dry_run", True), limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_lifecycle_compression":
        return bridge.lifecycle_compression(action=args.get("action", "review"), dry_run=args.get("dry_run", True), limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_reflex_status":
        return bridge.reflex_status(config_path=args.get("config_path"))
    if name == "super_memory_leitner":
        action = args.get("action", "queue")
        if action == "queue":
            return bridge.leitner_queue(limit=args.get("limit", 50), config_path=args.get("config_path"))
        elif action == "mark":
            return bridge.leitner_mark(args["memory_id"], success=args.get("success", True), config_path=args.get("config_path"))
        elif action == "schedule":
            return bridge.leitner_schedule(args["memory_id"], box=args.get("box", 0), config_path=args.get("config_path"))
        elif action == "stats":
            return bridge.leitner_stats(config_path=args.get("config_path"))
        elif action == "auto_seed":
            return bridge.leitner_auto_seed(limit=args.get("limit", 100), config_path=args.get("config_path"))
        else:
            raise ValueError(f"unknown leitner action: {action}")
    if name == "super_memory_train_local":
        return bridge.train_local(args["path"], domain_tag=args.get("domain_tag", "local"), recursive=args.get("recursive", True), limit=args.get("limit", 200), save=args.get("save", True), config_path=args.get("config_path"))
    if name == "super_memory_index_local":
        return bridge.index_local(args["path"], extensions=args.get("extensions"), recursive=args.get("recursive", True), limit=args.get("limit", 500), save=args.get("save", True), config_path=args.get("config_path"))
    if name == "super_memory_index_status":
        return bridge.index_status(config_path=args.get("config_path"))
    if name == "super_memory_import_local":
        return bridge.import_local(args["path"], source_name=args.get("source_name", "local-import"), recursive=args.get("recursive", True), limit=args.get("limit", 200), save=args.get("save", True), config_path=args.get("config_path"))
    if name == "super_memory_watch_scan":
        return bridge.watch_scan(args["directory"], recursive=args.get("recursive", True), limit=args.get("limit", 200), save=args.get("save", False), config_path=args.get("config_path"))
    if name == "super_memory_sync_status":
        return bridge.sync_status(config_path=args.get("config_path"))
    if name == "super_memory_store_status":
        return bridge.store_status(config_path=args.get("config_path"))

    # Cross-agent / cross-session Phase A+B+C tools
    phase_abc = {
        "super_memory_cross_agent_recall": (CrossAgentTools, "cross_agent_recall"),
        "super_memory_cross_agent_honcho_ask": (CrossAgentTools, "cross_agent_honcho_ask"),
        "super_memory_cross_agent_summary": (CrossAgentTools, "cross_agent_summary"),
        "super_memory_cross_agent_compare": (CrossAgentTools, "cross_agent_compare"),
        "super_memory_list_agents": (CrossAgentTools, "list_agents"),
        "super_memory_session_timeline": (SessionTimelineTools, "session_timeline"),
        "super_memory_session_list": (SessionTimelineTools, "session_list"),
        "super_memory_session_evolution": (SessionTimelineTools, "session_evolution"),
        "super_memory_session_search": (SessionTimelineTools, "session_search"),
        "super_memory_capture_event": (CaptureHook, "capture_event"),
        "super_memory_capture_turn": (CaptureHook, "capture_turn"),
        "super_memory_create_handoff": (HandoffTools, "create_handoff"),
        "super_memory_get_handoff": (HandoffTools, "get_handoff"),
        "super_memory_list_handoffs": (HandoffTools, "list_handoffs"),
        "super_memory_update_handoff_status": (HandoffTools, "update_handoff_status"),
        "super_memory_cross_session_synthesis": (SynthesisTools, "cross_session_synthesis"),
        "super_memory_shared_recall": (SynthesisTools, "shared_recall"),
        "super_memory_promote_to_shared": (SynthesisTools, "promote_to_shared"),
        "super_memory_cross_agent_conflicts": (SynthesisTools, "cross_agent_conflicts"),
    }
    if name in phase_abc:
        config_path = args.pop("config_path", None)
        cls, method = phase_abc[name]
        return getattr(cls(load_config(config_path)), method)(**args)

    # P0-P5 Optimization tools
    phase_p0_p5 = {
        "super_memory_post_turn_capture": (HookManager, "post_turn_capture"),
        "super_memory_session_start_context": (HookManager, "session_start_context"),
        "super_memory_session_end_summary": (HookManager, "session_end_summary"),
        "super_memory_delegation_handoff": (HookManager, "delegation_handoff"),
        "super_memory_cross_scope_recall": (HybridRecall, "cross_scope_recall"),
        "super_memory_extract_claims": (ClaimExtractor, "extract_claims_from_memory"),
        "super_memory_find_contradictions": (ClaimExtractor, "find_contradictions"),
        "super_memory_resolve_contradiction": (ClaimExtractor, "resolve_contradiction"),
        "super_memory_agent_belief_report": (ClaimExtractor, "agent_belief_report"),
        "super_memory_create_session_summary": (SessionArchive, "create_session_summary"),
        "super_memory_get_session_summary": (SessionArchive, "get_session_summary"),
        "super_memory_list_session_summaries": (SessionArchive, "list_session_summaries"),
        "super_memory_search_session_archives": (SessionArchive, "search_session_archives"),
        "super_memory_session_timeline_view": (SessionArchive, "session_timeline_view"),
        "super_memory_auto_handoff_on_spawn": (HandoffTools, "auto_handoff_on_spawn"),
        "super_memory_load_current_handoff": (HandoffTools, "load_current_handoff"),
        "super_memory_complete_handoff_with_outcome": (HandoffTools, "complete_handoff_with_outcome"),
        "super_memory_cross_agent_report": (Reports, "cross_agent_report"),
        "super_memory_session_health": (Reports, "session_health"),
        "super_memory_memory_pollution_report": (Reports, "memory_pollution_report"),
        "super_memory_export_memory_graph": (Reports, "export_memory_graph"),
    }
    if name in phase_p0_p5:
        config_path = args.pop("config_path", None)
        cls, method = phase_p0_p5[name]
        return getattr(cls(load_config(config_path)), method)(**args)

    # Phase 1 MemPalace tools
    if name.startswith("super_memory_palace_"):
        config_path = args.pop("config_path", None)
        config = load_config(config_path)
        tools = MemPalaceTools(config)
        action = name.replace("super_memory_palace_", "palace_")
        if not hasattr(tools, action):
            raise ValueError(f"unknown MemPalace action: {action}")
        return getattr(tools, action)(**args)

    # Phase 2 Honcho tools
    if name.startswith("super_memory_honcho_"):
        config_path = args.pop("config_path", None)
        config = load_config(config_path)
        tools = HonchoTools(config)
        action = name.replace("super_memory_honcho_", "honcho_")
        if not hasattr(tools, action):
            raise ValueError(f"unknown Honcho action: {action}")
        return getattr(tools, action)(**args)


    # ── Dream Engine (P0) ────────────────────────────────────
    if name == "super_memory_dream_insight_generation":
        return bridge.dream_insight_generation(limit=args.get("limit", 200), dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_dream_weak_tie_reinforcement":
        return bridge.dream_weak_tie_reinforcement(limit=args.get("limit", 200), dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_dream_pattern_summary":
        return bridge.dream_pattern_summary(limit=args.get("limit", 200), dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_dream_full_cycle":
        return bridge.dream_full_cycle(limit=args.get("limit", 200), dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    # ── Telemetry (P3) ───────────────────────────────────────
    if name == "super_memory_telemetry_record_event":
        return bridge.telemetry_record_event(args.get("kind"), agent_id=args.get("agent_id", "lucas"), tool_name=args.get("tool_name"), duration_ms=args.get("duration_ms"), success=args.get("success", True), detail=args.get("detail"), config_path=args.get("config_path"))
    if name == "super_memory_telemetry_stats":
        return bridge.telemetry_stats(days=args.get("days", 7), config_path=args.get("config_path"))
    if name == "super_memory_telemetry_aggregate_daily":
        return bridge.telemetry_aggregate_daily(config_path=args.get("config_path"))
    # ── Per-agent Isolation (P3) ─────────────────────────────
    if name == "super_memory_isolation_set_rules":
        return bridge.isolation_set_rules(args.get("agent_id"), allowed_scopes=args.get("allowed_scopes"), allowed_agents=args.get("allowed_agents"), blocked_agents=args.get("blocked_agents"), read_others=args.get("read_others"), config_path=args.get("config_path"))
    if name == "super_memory_isolation_get_rules":
        return bridge.isolation_get_rules(args.get("agent_id"), config_path=args.get("config_path"))
    if name == "super_memory_isolation_summary":
        return bridge.isolation_summary(config_path=args.get("config_path"))
    if name == "super_memory_isolation_agent_counts":
        return bridge.isolation_agent_counts(config_path=args.get("config_path"))
    # ── Auto-complete ───────────────────────────────────────
    if name == "super_memory_autocomplete_suggest":
        return bridge.autocomplete_suggest(args.get("prefix"), limit=args.get("limit", 5), type_filter=args.get("type_filter"), config_path=args.get("config_path"))
    if name == "super_memory_autocomplete_idle":
        return bridge.autocomplete_idle(config_path=args.get("config_path"))
    if name == "super_memory_autocomplete_rebuild":
        return bridge.autocomplete_rebuild(config_path=args.get("config_path"))
    if name == "super_memory_autocomplete_status":
        return bridge.autocomplete_status(config_path=args.get("config_path"))
    if name == "super_memory_recommendations":
        return bridge.recommendations(limit=args.get("limit", 10), config_path=args.get("config_path"))
    # ── Auto Deep Pipeline ───────────────────────────────────
    if name == "super_memory_deep_audit":
        return bridge.deep_audit(config_path=args.get("config_path"))
    if name == "super_memory_deep_qualify":
        return bridge.deep_qualify(config_path=args.get("config_path"))
    if name == "super_memory_deep_debug":
        return bridge.deep_debug(config_path=args.get("config_path"))
    if name == "super_memory_deep_improve":
        return bridge.deep_improve(dry_run=args.get("dry_run", True), config_path=args.get("config_path"), async_mode=args.get("async_mode", True), compact=args.get("compact", True), max_seconds=args.get("max_seconds", 3))
    if name == "super_memory_auto_deep_pipeline":
        return bridge.auto_deep_pipeline(dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_capture_failed_recall":
        return bridge.capture_failed_recall(query=args.get("query", ""), wrong_answer=args.get("wrong_answer", ""), expected_answer=args.get("expected_answer", ""), notes=args.get("notes", ""), config_path=args.get("config_path"))
    if name == "super_memory_project_state_update":
        return bridge.project_state_update(project=args.get("project", "super-memory-github"), summary=args.get("summary", ""), facts=args.get("facts") or {}, config_path=args.get("config_path"))
    if name == "super_memory_issue_memory_update":
        return bridge.issue_memory_update(title=args.get("title", ""), status=args.get("status", "open"), cause=args.get("cause", ""), fix=args.get("fix", ""), verification=args.get("verification", ""), config_path=args.get("config_path"))
    # ── P0: MemoryEnvelope ───────────────────────────────────
    if name == "super_memory_build_envelope":
        return bridge.build_envelope(args.get("content"), memory_type=args.get("memory_type"), scope=args.get("scope"), agent_id=args.get("agent_id", "lucas"), session_id=args.get("session_id"), project=args.get("project"), tags=args.get("tags"), source_adapter=args.get("source_adapter", "direct"), trust_score=args.get("trust_score"), lifecycle_tier=args.get("lifecycle_tier", "warm"), auto_pin=args.get("auto_pin", False), config_path=args.get("config_path"))
    if name == "super_memory_remember_through_envelope":
        return bridge.remember_through_envelope(args.get("content"), memory_type=args.get("memory_type"), scope=args.get("scope"), agent_id=args.get("agent_id", "lucas"), session_id=args.get("session_id"), project=args.get("project"), tags=args.get("tags"), source_adapter=args.get("source_adapter", "direct"), trust_score=args.get("trust_score"), lifecycle_tier=args.get("lifecycle_tier", "warm"), auto_pin=args.get("auto_pin", False), config_path=args.get("config_path"))
    # ── P0: SourceAdapter ────────────────────────────────────
    if name == "super_memory_ingest_through_adapter":
        return bridge.ingest_through_adapter(args.get("source_path"), agent_id=args.get("agent_id", "lucas"), session_id=args.get("session_id"), project=args.get("project"), config_path=args.get("config_path"))
    if name == "super_memory_list_source_adapters":
        return bridge.list_source_adapters(config_path=args.get("config_path"))
    if name == "super_memory_ingest_and_remember":
        return bridge.ingest_and_remember(args.get("source_path"), agent_id=args.get("agent_id", "lucas"), session_id=args.get("session_id"), project=args.get("project"), config_path=args.get("config_path"))
    # ── P0: Semantic Closets ─────────────────────────────────
    if name == "super_memory_build_closets":
        return bridge.build_closets_for_memory(args.get("memory_id"), config_path=args.get("config_path"))
    if name == "super_memory_rebuild_all_closets":
        return bridge.rebuild_all_closets(limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_search_closets":
        return bridge.search_closets(args.get("query"), limit=args.get("limit", 10), config_path=args.get("config_path"))
    if name == "super_memory_hydrate_drawers":
        return bridge.hydrate_drawers(drawer_ids=args.get("drawer_ids"), closet_ids=args.get("closet_ids"), config_path=args.get("config_path"))
    if name == "super_memory_closet_stats":
        return bridge.closet_stats(config_path=args.get("config_path"))
    # ── P0: Recall Arbitration v3 ────────────────────────────
    if name == "super_memory_recall_arbitrate_v3":
        return bridge.recall_arbitrate_v3(args.get("query"), limit=args.get("limit", 10), config_path=args.get("config_path"), min_score=args.get("min_score", 0.0))
    if name == "super_memory_recall_quick":
        return bridge.recall_quick(args.get("query"), limit=args.get("limit", 5), config_path=args.get("config_path"))
    # ── P0: Recall Feedback Loop ─────────────────────────────
    if name == "super_memory_recall_record_event":
        return bridge.recall_record_event(args.get("query"), args.get("selected_memory_ids", []), shown_to_user=args.get("shown_to_user", True), config_path=args.get("config_path"))
    if name == "super_memory_recall_record_feedback":
        return bridge.recall_record_feedback(args.get("recall_event_id"), args.get("memory_id"), args.get("outcome"), confidence=args.get("confidence", 1.0), notes=args.get("notes", ""), config_path=args.get("config_path"))
    if name == "super_memory_recall_record_correction":
        return bridge.recall_record_correction(args.get("query"), args.get("memory_id", ""), wrong_answer=args.get("wrong_answer", ""), expected_answer=args.get("expected_answer", ""), notes=args.get("notes", ""), config_path=args.get("config_path"))
    if name == "super_memory_recall_feedback_stats":
        return bridge.recall_feedback_stats(config_path=args.get("config_path"))
    if name == "super_memory_recall_generate_training_cases":
        return bridge.recall_generate_training_cases(min_corrections=args.get("min_corrections", 3), config_path=args.get("config_path"))
    if name == "super_memory_recall_benchmark_seed":
        return bridge.recall_benchmark_seed(config_path=args.get("config_path"), overwrite=args.get("overwrite", False))
    if name == "super_memory_recall_release_gate":
        return bridge.recall_release_gate(config_path=args.get("config_path"), limit=args.get("limit", 100))
    if name == "super_memory_scheduled_maintenance_report":
        return bridge.scheduled_maintenance_report(config_path=args.get("config_path"), dry_run=args.get("dry_run", False), profile=args.get("profile", "daily"))
    # ── P2: Projection Drift Repair ──────────────────────────
    if name == "super_memory_audit_drift":
        return bridge.audit_drift(config_path=args.get("config_path"))
    if name == "super_memory_repair_orphans":
        return bridge.repair_orphans(dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_full_drift_repair":
        return bridge.full_drift_repair(dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_register_projection":
        return bridge.register_projection(table_name=args.get("table_name"), memory_id=args.get("memory_id"), projection_key=args.get("projection_key"), config_path=args.get("config_path"))
    # ── P2: Adapter-driven Watcher ───────────────────────────
    if name == "super_memory_adapter_scan_once":
        return bridge.adapter_scan_once(directories=args.get("directories"), exclude=args.get("exclude"), config_path=args.get("config_path"))
    if name == "super_memory_adapter_settle_scan":
        return bridge.adapter_settle_scan(directories=args.get("directories"), exclude=args.get("exclude"), config_path=args.get("config_path"))
    if name == "super_memory_adapter_monitor_status":
        return bridge.adapter_monitor_status(config_path=args.get("config_path"))
    # ── P2: Line Citations / Neighbor Expansion ──────────────
    if name == "super_memory_enrich_recall_with_citations":
        return bridge.enrich_recall_with_citations(recall_result=args.get("recall_result", {}), neighbor_lines=args.get("neighbor_lines", 3), config_path=args.get("config_path"))
    if name == "super_memory_track_source":
        return bridge.track_source(memory_id=args.get("memory_id"), file_path=args.get("file_path"), line_start=args.get("line_start", 0), config_path=args.get("config_path"))
    # ── P2: Agentic Dialectic Mode ───────────────────────────
    if name == "super_memory_dialectic_answer":
        return bridge.dialectic_answer(query=args.get("query"), recall_result=args.get("recall_result"), mode=args.get("mode", "format"), config_path=args.get("config_path"))
    # ── P2: Self-Education Curriculum ────────────────────────
    if name == "super_memory_analyze_recall_failures":
        return bridge.analyze_recall_failures(config_path=args.get("config_path"))
    if name == "super_memory_generate_curriculum":
        return bridge.generate_curriculum(config_path=args.get("config_path"))
    if name == "super_memory_run_benchmark_tests":
        return bridge.run_benchmark_tests(config_path=args.get("config_path"))
    # ── P0/P2 fixes: forget + edit ──────────────────────────
    if name == "super_memory_forget":
        return bridge.forget(args.get("memory_id"), hard=args.get("hard", False), reason=args.get("reason", ""), config_path=args.get("config_path"))
    if name == "super_memory_edit":
        return bridge.edit(args.get("memory_id"), content=args.get("content"), type=args.get("type"), priority=args.get("priority"), tier=args.get("tier"), config_path=args.get("config_path"))
    
    # ── Execution Patterns (v2.4.0) ──────────────────────────
    if name == "super_memory_route_task":
        return mcp_execution_tools.route_task(
            duration_min=args["duration_min"],
            steps=args["steps"],
            files=args.get("files", 0),
            complexity=args.get("complexity", "medium")
        )
    if name == "super_memory_create_execution_contract":
        return {"contract_file": mcp_execution_tools.create_execution_contract(
            task=args["task"],
            mode=args["mode"],
            steps=args["steps"],
            estimated_time=args["estimated_time"],
            checkpoints=args["checkpoints"],
            auto_continue=args.get("auto_continue", True)
        )}
    if name == "super_memory_create_plan":
        return {"plan_file": mcp_execution_tools.create_plan_file(
            task_description=args["task_description"],
            steps=args["steps"],
            mode=args["mode"],
            estimated_time=args["estimated_time"],
            session_id=args.get("session_id")
        )}
    if name == "super_memory_update_plan_progress":
        success = mcp_execution_tools.update_plan_progress(
            plan_file=args["plan_file"],
            step_index=args["step_index"],
            status=args["status"]
        )
        return {"success": success}
    if name == "super_memory_recover_incomplete_tasks":
        return {"incomplete_tasks": mcp_execution_tools.recover_incomplete_tasks(
            max_age_hours=args.get("max_age_hours", 24),
            limit=args.get("limit", 10)
        )}
    if name == "super_memory_detect_memory_loss":
        return mcp_execution_tools.detect_memory_loss()

    raise ValueError(f"unknown tool: {name}")


def _response(request_id: Any, result: Any) -> JSON:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, data: Any | None = None) -> JSON:
    payload: JSON = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    if data is not None:
        payload["error"]["data"] = data
    return payload


def handle(request: JSON) -> JSON | None:
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        return _response(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "Super Memory MCP is a project-local memory server. Workspace Markdown remains canonical; "
                    "MCP tools are derived/programmatic access. Do not apply/register into this machine's OpenClaw config unless explicitly instructed. "
                    f"Active MCP profile: {MCP_PROFILE}."
                ),
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _response(request_id, {})
    if method == "tools/list":
        return _response(request_id, {"tools": _tool_descriptors()})
    if method == "tools/call":
        name = params.get("name")
        args = dict(params.get("arguments") or {})
        try:
            result = _call_tool(name, args)
        except PermissionError as exc:
            return _error(request_id, -32000, str(exc))
        return _response(request_id, {"content": _text(result), "isError": False})
    if method == "resources/list":
        return _response(request_id, {"resources": [{"uri": "super-memory://status", "name": "Super Memory status", "mimeType": "application/json"}]})
    if method == "resources/read":
        uri = params.get("uri")
        if uri != "super-memory://status":
            return _error(request_id, -32602, f"unknown resource: {uri}")
        return _response(request_id, {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(bridge.status(), ensure_ascii=False, indent=2)}]})
    return _error(request_id, -32601, f"method not found: {method}")


def serve() -> None:
    DEBUG = os.environ.get("SUPER_MEMORY_MCP_DEBUG", "0") in ("1", "true", "yes")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle(request)
        except Exception as exc:  # keep MCP transport alive and report as JSON-RPC error
            data = traceback.format_exc() if DEBUG else f"{type(exc).__name__}: {exc}"
            response = _error(None, -32000, str(exc), data)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def main(argv: list[str] | None = None) -> None:
    global MCP_PROFILE
    parser = argparse.ArgumentParser(description="Super Memory MCP stdio server")
    parser.add_argument("--stdio", action="store_true", help="Run stdio MCP server (default)")
    parser.add_argument(
        "--profile",
        choices=["normal", "admin", "all"],
        default=os.environ.get("SUPER_MEMORY_MCP_PROFILE", "normal"),
        help="Tool exposure profile. normal is safe default; admin exposes promotion; all exposes every tool.",
    )
    args = parser.parse_args(argv)
    MCP_PROFILE = args.profile
    serve()


if __name__ == "__main__":
    main()
