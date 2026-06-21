from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from typing import Any

from . import bridge
from .capture_hook import CAPTURE_HOOK_TOOLS, CaptureHook
from .claim_extractor import CLAIM_EXTRACTOR_TOOLS, ClaimExtractor
from .config import load_config
from .cross_agent import CROSS_AGENT_TOOLS, CrossAgentTools
from .handoff import HANDOFF_TOOLS, HandoffTools
from .honcho.tools import HONCHO_TOOLS, HonchoTools
from .hooks import HOOKS_TOOLS, HookManager
from .hybrid_recall import HYBRID_RECALL_TOOLS, HybridRecall
from .mempalace.tools import MEMPALACE_TOOLS, MemPalaceTools
from .reports import REPORTS_TOOLS, Reports
from .session_archive import SESSION_ARCHIVE_TOOLS, SessionArchive
from .session_timeline import SESSION_TIMELINE_TOOLS, SessionTimelineTools
from .synthesis import SYNTHESIS_TOOLS, SynthesisTools

JSON = dict[str, Any]

SERVER_INFO = {"name": "super-memory", "version": "1.1.3"}
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
    "super_memory_auto_compact",
    "super_memory_cleanup",
    "super_memory_sanitize_prompt",
    "super_memory_sanitize_auto_capture",
    "super_memory_normalize_memory",
    "super_memory_recall",
    "super_memory_prefetch",
    "super_memory_sync_turn",
    "super_memory_durable_pack",
    "super_memory_durable_pack_status",
    "super_memory_durable_pack_audit",
    "super_memory_memory_search",
    "super_memory_memory_get",
    "super_memory_status",
    # P1: Write Queue
    "super_memory_write_queue_flush",
    "super_memory_write_queue_defer",
    # P1: Depth Prior
    "super_memory_depth_prior_status",
    # P2: Conflict Detection
    "super_memory_detect_conflicts",
    "super_memory_resolve_conflict",
    # P2: Versioning
    "super_memory_version_create",
    "super_memory_version_list",
    "super_memory_version_diff",
    "super_memory_version_rollback_dry_run",
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
    "super_memory_hypothesis_create",
    "super_memory_hypothesis_get",
    "super_memory_hypothesis_list",
    "super_memory_evidence_add",
    "super_memory_prediction_create",
    "super_memory_prediction_list",
    "super_memory_verify_prediction",
    "super_memory_lifecycle_review",
    "super_memory_lifecycle_quality_cleanup",
    "super_memory_lifecycle_cache",
    "super_memory_lifecycle_tier",
    "super_memory_lifecycle_compression",
    "super_memory_embedding_doctor",
    "super_memory_embedding_auto_select",
    "super_memory_semantic_doctor",
    "super_memory_semantic_index",
    "super_memory_semantic_verify",
    "super_memory_semantic_quality_audit",
    "super_memory_maintenance_run",
    "super_memory_short_term_audit",
    "super_memory_short_term_repair",
    "super_memory_short_term_mark_reviewed",
    "super_memory_dreaming_audit",
    "super_memory_dreaming_run",
    "super_memory_dreaming_repair",
    "super_memory_reflex_status",
    "super_memory_leitner",
    "super_memory_leitner_due",
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
    "super_memory_sync_archive_to_honcho",
    "super_memory_store_status",
    "super_memory_diagnostics",
    "super_memory_cross_layer_health",
    "super_memory_backfill_markdown_sqlite",
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
    "super_memory_session_health",
    "super_memory_memory_pollution_report",
    "super_memory_export_memory_graph",
}
ADMIN_TOOLS = ADMIN_TOOLS | ADVANCED_TOOLS


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
    "super_memory_cross_layer_health": {
        "description": "Audit cross-layer consistency: canonical markdown rows, projection orphans, content drift, and pending sync.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_backfill_markdown_sqlite": {
        "description": "Admin repair: backfill missing workspace_markdown SQLite rows from existing derived-layer records.",
        "inputSchema": _schema({"limit": {"type": "integer", "default": 2000}, "config_path": {"type": "string"}}),
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
    "super_memory_health": {
        "description": "Check Super Memory consistency guardrails: canonical-first and workspace markdown enabled.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
    "super_memory_auto_compact": {
        "description": "Auto-compact soft-deleted records when ratio exceeds threshold (default 20%). Safe by default (dry_run=True).",
        "inputSchema": {"type": "object", "properties": {
            "threshold": {"type": "number", "default": 0.2},
            "dry_run": {"type": "boolean", "default": True},
            "config_path": {"type": "string"}
        }},
    },
    "super_memory_cleanup": {
        "description": "Official safe SQLite cleanup: migrations, derived views, FTS rebuilds, transactions, optional VACUUM.",
        "inputSchema": _schema(
            {
                "config_path": {"type": "string"},
                "vacuum": {"type": "boolean", "default": False},
                "integrity_check": {"type": "boolean", "default": True},
            }
        ),
    },
    "super_memory_prune": {
        "description": "Prune memories matching retention policy criteria. Safe by default (dry_run=True). Built-in: empty openclaw.turn events + optional source_prefixes/max_days filter.",
        "inputSchema": _schema(
            {
                "config_path": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
                "source_prefixes": {"type": "array", "items": {"type": "string"}},
                "max_days": {"type": "integer"},
            }
        ),
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
    "super_memory_durable_pack": {
        "description": "Install curated shared/project durable memories for OpenClaw agents, then auto-qualify and debug recall.",
        "inputSchema": _schema(
            {
                "pack_name": {"type": "string", "default": "openclaw-super-memory-durable-pack-v1"},
                "project": {"type": "string", "default": "super-memory"},
                "agents": {"type": "array", "items": {"type": "string"}},
                "qualify": {"type": "boolean", "default": True},
                "debug": {"type": "boolean", "default": True},
                "dedupe": {"type": "boolean", "default": True},
                "config_path": {"type": "string"},
            }
        ),
    },
    "super_memory_durable_pack_status": {
        "description": "Audit whether the curated OpenClaw durable memory pack is installed, qualified, and duplicate-free.",
        "inputSchema": _schema(
            {
                "pack_name": {"type": "string", "default": "openclaw-super-memory-durable-pack-v1"},
                "project": {"type": "string", "default": "super-memory"},
                "config_path": {"type": "string"},
            }
        ),
    },
    "super_memory_durable_pack_audit": {
        "description": "Deep audit the OpenClaw durable memory pack; with fix=true, soft-delete duplicates and backfill SQLite-only canonical rows.",
        "inputSchema": _schema(
            {
                "pack_name": {"type": "string", "default": "openclaw-super-memory-durable-pack-v1"},
                "project": {"type": "string", "default": "super-memory"},
                "fix": {"type": "boolean", "default": False},
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
}

for _tool in MEMPALACE_TOOLS + HONCHO_TOOLS + CROSS_AGENT_TOOLS + SESSION_TIMELINE_TOOLS + CAPTURE_HOOK_TOOLS + HANDOFF_TOOLS + SYNTHESIS_TOOLS + HOOKS_TOOLS + HYBRID_RECALL_TOOLS + CLAIM_EXTRACTOR_TOOLS + SESSION_ARCHIVE_TOOLS + REPORTS_TOOLS:
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
    ("super_memory_hypothesis_create", "Create a deterministic cognitive hypothesis.", {"content": {"type": "string"}, "confidence": {"type": "number", "default": 0.5}, "tags": {"type": "array", "items": {"type": "string"}}, "config_path": {"type": "string"}}, ["content"]),
    ("super_memory_hypothesis_get", "Get hypothesis detail with evidence/predictions.", {"hypothesis_id": {"type": "string"}, "config_path": {"type": "string"}}, ["hypothesis_id"]),
    ("super_memory_hypothesis_list", "List hypotheses.", {"status": {"type": "string"}, "limit": {"type": "integer", "default": 20}, "config_path": {"type": "string"}}, []),
    ("super_memory_evidence_add", "Add evidence for/against a hypothesis.", {"hypothesis_id": {"type": "string"}, "content": {"type": "string"}, "direction": {"type": "string", "default": "for"}, "weight": {"type": "number", "default": 0.5}, "config_path": {"type": "string"}}, ["hypothesis_id", "content"]),
    ("super_memory_prediction_create", "Create a falsifiable prediction.", {"content": {"type": "string"}, "confidence": {"type": "number", "default": 0.7}, "hypothesis_id": {"type": "string"}, "deadline": {"type": "string"}, "config_path": {"type": "string"}}, ["content"]),
    ("super_memory_prediction_list", "List predictions.", {"status": {"type": "string"}, "limit": {"type": "integer", "default": 20}, "config_path": {"type": "string"}}, []),
    ("super_memory_verify_prediction", "Verify a prediction as correct/wrong.", {"prediction_id": {"type": "string"}, "outcome": {"type": "string"}, "content": {"type": "string"}, "config_path": {"type": "string"}}, ["prediction_id", "outcome"]),
    ("super_memory_lifecycle_review", "Review lifecycle hygiene.", {"limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_lifecycle_quality_cleanup", "Soft-delete active duplicate memory IDs and mark long raw event transcripts for compression without hard deletion.", {"dry_run": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_lifecycle_cache", "Manage local activation cache status/save/load/clear.", {"action": {"type": "string", "default": "status"}, "config_path": {"type": "string"}}, []),
    ("super_memory_lifecycle_tier", "Evaluate/apply deterministic memory tiers.", {"action": {"type": "string", "default": "evaluate"}, "dry_run": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_lifecycle_compression", "Review/mark compression candidates without truncating content.", {"action": {"type": "string", "default": "review"}, "dry_run": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_embedding_doctor", "Inspect embedding/semantic provider health and recommend FTS or semantic mode.", {"config_path": {"type": "string"}}, []),
    ("super_memory_embedding_auto_select", "Choose the healthiest local recall backend using doctor metadata.", {"config_path": {"type": "string"}}, []),
    ("super_memory_semantic_doctor", "Run semantic sqlite-vec/Ollama doctor checks.", {"query": {"type": "string", "default": "semantic recall smoke test"}, "config_path": {"type": "string"}}, []),
    ("super_memory_semantic_index", "Incrementally index canonical workspace memories into sqlite-vec.", {"rebuild": {"type": "boolean", "default": False}, "batch_size": {"type": "integer", "default": 8}, "limit": {"type": "integer"}, "config_path": {"type": "string"}}, []),
    ("super_memory_semantic_verify", "Verify semantic KNN recall and hydrate canonical memories.", {"query": {"type": "string", "default": "semantic recall smoke test"}, "limit": {"type": "integer", "default": 5}, "config_path": {"type": "string"}}, []),
    ("super_memory_semantic_quality_audit", "Check known durable queries rank high in semantic retrieval.", {"config_path": {"type": "string"}}, []),
    ("super_memory_maintenance_run", "Run safe maintenance: cleanup, semantic index, short-term policy, dreaming, health checks.", {"dry_run": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_short_term_audit", "Audit short-term event memories for promotion candidates.", {"limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_short_term_repair", "Promote high-signal short-term event clusters into curated memories and mark raw events for compression.", {"dry_run": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
    ("super_memory_short_term_mark_reviewed", "Mark a short-term promotion cluster as reviewed/promoted/deferred/ignored.", {"cluster_key": {"type": "string"}, "decision": {"type": "string", "default": "deferred"}, "config_path": {"type": "string"}}, ["cluster_key"]),
    ("super_memory_dreaming_audit", "Audit inputs for dreaming/sleep consolidation artifacts.", {"config_path": {"type": "string"}}, []),
    ("super_memory_dreaming_run", "Create a deterministic dreaming consolidation artifact and optional insight memory.", {"dry_run": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 200}, "config_path": {"type": "string"}}, []),
    ("super_memory_dreaming_repair", "Inspect dreaming artifacts and recommend non-destructive repair/run actions.", {"config_path": {"type": "string"}}, []),
    ("super_memory_write_queue_flush", "Flush the deferred write queue (batch save pending records).", {"queue_key": {"type": "string", "default": "default"}, "config_path": {"type": "string"}}, []),
    ("super_memory_write_queue_defer", "Defer a memory record to the write queue for batch flush.", {"content": {"type": "string"}, "type_": {"type": "string", "default": "context"}, "scope": {"type": "string", "default": "session"}, "agent_id": {"type": "string", "default": "lucas"}, "tags": {"type": "array", "items": {"type": "string"}}, "config_path": {"type": "string"}}, ["content"]),
    ("super_memory_depth_prior_status", "Show depth prior adaptation state (query type depths, success rates).", {"config_path": {"type": "string"}}, []),
    ("super_memory_detect_conflicts", "Detect conflicting memories via negation/temporal analysis.", {"content": {"type": "string"}, "min_similarity": {"type": "number", "default": 0.3}, "limit": {"type": "integer", "default": 50}, "config_path": {"type": "string"}}, []),
    ("super_memory_resolve_conflict", "Resolve a detected conflict.", {"conflict_key": {"type": "string"}, "resolution": {"type": "string", "enum": ["keep_both", "keep_a", "keep_b", "supersede"]}, "reason": {"type": "string", "default": ""}, "config_path": {"type": "string"}}, ["conflict_key", "resolution"]),
    ("super_memory_version_create", "Create a brain version snapshot for safe rollback.", {"name": {"type": "string", "default": "snapshot"}, "description": {"type": "string", "default": ""}, "config_path": {"type": "string"}}, []),
    ("super_memory_version_list", "List all version snapshots.", {"config_path": {"type": "string"}}, []),
    ("super_memory_version_diff", "Diff two version snapshots.", {"from_version": {"type": "string"}, "to_version": {"type": "string"}, "config_path": {"type": "string"}}, ["from_version", "to_version"]),
    ("super_memory_version_rollback_dry_run", "Preview rollback to a snapshot (non-destructive dry-run).", {"version_id": {"type": "string"}, "config_path": {"type": "string"}}, ["version_id"]),
    ("super_memory_leitner", "Leitner 5-box: queue|mark|schedule|stats|auto_seed.", {"action": {"type": "string", "default": "queue"}, "memory_id": {"type": "string"}, "success": {"type": "boolean", "default": True}, "box": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 50}, "config_path": {"type": "string"}}, []),
    ("super_memory_leitner_due", "Return count of Leitner-due memories without loading full queue.", {"config_path": {"type": "string"}}, []),
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

def _allowed_tools(profile: str | None = None) -> set[str]:
    effective = (profile or MCP_PROFILE or "normal").lower()
    try:
        return _ALLOWED_CACHE[effective]
    except KeyError:
        pass
    if effective == "admin":
        result = ADMIN_TOOLS
    elif effective == "all":
        result = set(TOOLS)
    else:
        result = NORMAL_TOOLS
    _ALLOWED_CACHE[effective] = result
    return result

_ALLOWED_CACHE: dict[str, set[str]] = {}


def _tool_descriptors(profile: str | None = None) -> list[JSON]:
    effective = (profile or MCP_PROFILE or "normal").lower()
    try:
        return _DESCRIPTOR_CACHE[effective]
    except KeyError:
        pass
    allowed = _allowed_tools(profile)
    result = [{"name": name, **meta} for name, meta in TOOLS.items() if name in allowed]
    _DESCRIPTOR_CACHE[effective] = result
    return result

_DESCRIPTOR_CACHE: dict[str, list[JSON]] = {}


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
    if name == "super_memory_cross_layer_health":
        return bridge.cross_layer_health(config_path=args.get("config_path"))
    if name == "super_memory_backfill_markdown_sqlite":
        return bridge.backfill_markdown_sqlite(limit=args.get("limit", 2000), config_path=args.get("config_path"))
    if name == "super_memory_memory_slot_contract":
        return bridge.memory_slot_contract(config_path=args.get("config_path"))
    if name == "super_memory_mcp_contract":
        return bridge.mcp_contract(profile=args.get("profile", "admin"), config_path=args.get("config_path"))
    if name == "super_memory_supervised_runtime_smoke":
        return bridge.supervised_runtime_smoke(config_path=args.get("config_path"))
    if name == "super_memory_health":
        return bridge.health(config_path=args.get("config_path"))
    if name == "super_memory_auto_compact":
        return bridge.auto_compact(
            threshold=args.get("threshold", 0.2),
            dry_run=args.get("dry_run", True),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_cleanup":
        return bridge.cleanup(
            config_path=args.get("config_path"),
            vacuum=args.get("vacuum", False),
            integrity_check=args.get("integrity_check", True),
        )
    if name == "super_memory_prune":
        return bridge.prune(
            config_path=args.get("config_path"),
            dry_run=args.get("dry_run", True),
            source_prefixes=args.get("source_prefixes"),
            max_days=args.get("max_days"),
        )
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
    if name == "super_memory_durable_pack":
        return bridge.durable_pack(
            pack_name=args.get("pack_name", "openclaw-super-memory-durable-pack-v1"),
            project=args.get("project", "super-memory"),
            agents=args.get("agents") or ["lucas", "alex", "max", "isol"],
            qualify=args.get("qualify", True),
            debug=args.get("debug", True),
            dedupe=args.get("dedupe", True),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_durable_pack_status":
        return bridge.durable_pack_status(
            pack_name=args.get("pack_name", "openclaw-super-memory-durable-pack-v1"),
            project=args.get("project", "super-memory"),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_durable_pack_audit":
        return bridge.durable_pack_audit(
            pack_name=args.get("pack_name", "openclaw-super-memory-durable-pack-v1"),
            project=args.get("project", "super-memory"),
            fix=args.get("fix", False),
            config_path=args.get("config_path"),
        )
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
    if name == "super_memory_lifecycle_quality_cleanup":
        return bridge.lifecycle_quality_cleanup(dry_run=args.get("dry_run", True), limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_lifecycle_cache":
        return bridge.lifecycle_cache(action=args.get("action", "status"), config_path=args.get("config_path"))
    if name == "super_memory_lifecycle_tier":
        return bridge.lifecycle_tier(action=args.get("action", "evaluate"), dry_run=args.get("dry_run", True), limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_lifecycle_compression":
        return bridge.lifecycle_compression(action=args.get("action", "review"), dry_run=args.get("dry_run", True), limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_embedding_doctor":
        return bridge.embedding_doctor(config_path=args.get("config_path"))
    if name == "super_memory_embedding_auto_select":
        return bridge.embedding_auto_select(config_path=args.get("config_path"))
    if name == "super_memory_semantic_doctor":
        return bridge.semantic_doctor(config_path=args.get("config_path"), query=args.get("query", "semantic recall smoke test"))
    if name == "super_memory_semantic_index":
        return bridge.semantic_index(config_path=args.get("config_path"), rebuild=args.get("rebuild", False), batch_size=args.get("batch_size", 8), limit=args.get("limit"))
    if name == "super_memory_semantic_verify":
        return bridge.semantic_verify(config_path=args.get("config_path"), query=args.get("query", "semantic recall smoke test"), limit=args.get("limit", 5))
    if name == "super_memory_semantic_quality_audit":
        return bridge.semantic_quality_audit(config_path=args.get("config_path"))
    if name == "super_memory_maintenance_run":
        return bridge.maintenance_run(dry_run=args.get("dry_run", True), limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_short_term_audit":
        return bridge.short_term_audit(limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_short_term_repair":
        return bridge.short_term_repair(limit=args.get("limit", 500), dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_short_term_mark_reviewed":
        return bridge.short_term_mark_reviewed(cluster_key=args["cluster_key"], decision=args.get("decision", "deferred"), config_path=args.get("config_path"))
    if name == "super_memory_dreaming_audit":
        return bridge.dreaming_audit(config_path=args.get("config_path"))
    if name == "super_memory_dreaming_run":
        return bridge.dreaming_run(limit=args.get("limit", 200), dry_run=args.get("dry_run", True), config_path=args.get("config_path"))
    if name == "super_memory_write_queue_flush":
        return bridge.write_queue_flush(
            queue_key=args.get("queue_key", "default"),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_write_queue_defer":
        return bridge.write_queue_defer(
            content=args["content"],
            type_=args.get("type_", "context"),
            scope=args.get("scope", "session"),
            agent_id=args.get("agent_id", "lucas"),
            tags=args.get("tags"),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_depth_prior_status":
        return bridge.depth_prior_status(config_path=args.get("config_path"))
    if name == "super_memory_detect_conflicts":
        return bridge.detect_conflicts(
            content=args.get("content"),
            min_similarity=args.get("min_similarity", 0.3),
            limit=args.get("limit", 50),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_resolve_conflict":
        return bridge.resolve_conflict(
            conflict_key=args["conflict_key"],
            resolution=args["resolution"],
            reason=args.get("reason", ""),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_version_create":
        return bridge.version_create(
            name=args.get("name", "snapshot"),
            description=args.get("description", ""),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_version_list":
        return bridge.version_list(config_path=args.get("config_path"))
    if name == "super_memory_version_diff":
        return bridge.version_diff(
            from_version=args["from_version"],
            to_version=args["to_version"],
            config_path=args.get("config_path"),
        )
    if name == "super_memory_version_rollback_dry_run":
        return bridge.version_rollback_dry_run(
            version_id=args["version_id"],
            config_path=args.get("config_path"),
        )
    if name == "super_memory_dreaming_repair":
        return bridge.dreaming_repair(config_path=args.get("config_path"))
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
    if name == "super_memory_leitner_due":
        return bridge.leitner_due(config_path=args.get("config_path"))
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


class _StdoutToStderr:
    """Redirect accidental library logs/prints away from MCP stdout.

    MCP stdio stdout is a JSON-RPC transport and must never contain human logs.
    This proxy lets the server write protocol frames through _ORIGINAL_STDOUT
    while third-party logging/print calls are safely sent to stderr.
    """

    def write(self, data: str) -> int:
        return sys.stderr.write(data)

    def flush(self) -> None:
        sys.stderr.flush()


_ORIGINAL_STDOUT = sys.stdout

def _prepare_stdio_transport() -> None:
    sys.stdout = _StdoutToStderr()  # type: ignore[assignment]

def serve() -> None:
    _prepare_stdio_transport()
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
            _ORIGINAL_STDOUT.write(json.dumps(response, ensure_ascii=False) + "\n")
            _ORIGINAL_STDOUT.flush()


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
