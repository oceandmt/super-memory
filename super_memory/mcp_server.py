from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from typing import Any, Callable

from . import bridge

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
    "super_memory_graph_rebuild",
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
    "super_memory_train_local",
    "super_memory_import_local",
    "super_memory_watch_scan",
    "super_memory_sync_status",
    "super_memory_store_status",
    "super_memory_diagnostics",
    "super_memory_memory_slot_contract",
    "super_memory_mcp_contract",
    "super_memory_supervised_runtime_smoke",
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
    ("super_memory_graph_rebuild", "Rebuild derived Layer 4 graph from SQLite memories.", {"limit": {"type": "integer", "default": 500}, "config_path": {"type": "string"}}, []),
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
    ("super_memory_reflex_status", "Show reflex audit events and missing refs.", {"config_path": {"type": "string"}}, []),
    ("super_memory_train_local", "Train from local markdown/text under workspace only.", {"path": {"type": "string"}, "domain_tag": {"type": "string", "default": "local"}, "recursive": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 200}, "save": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, ["path"]),
    ("super_memory_import_local", "Import local markdown/text/json/jsonl under workspace only.", {"path": {"type": "string"}, "source_name": {"type": "string", "default": "local-import"}, "recursive": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 200}, "save": {"type": "boolean", "default": True}, "config_path": {"type": "string"}}, ["path"]),
    ("super_memory_watch_scan", "One-shot file watch scan; no daemon.", {"directory": {"type": "string"}, "recursive": {"type": "boolean", "default": True}, "limit": {"type": "integer", "default": 200}, "save": {"type": "boolean", "default": False}, "config_path": {"type": "string"}}, ["directory"]),
    ("super_memory_sync_status", "Show sync status only; cloud disabled.", {"config_path": {"type": "string"}}, []),
    ("super_memory_store_status", "Show store status only; community store disabled.", {"config_path": {"type": "string"}}, []),
]:
    TOOLS[_name] = {"description": _desc, "inputSchema": _schema(_props, _required)}

def _allowed_tools(profile: str | None = None) -> set[str]:
    effective = (profile or MCP_PROFILE or "normal").lower()
    if effective == "admin":
        return ADMIN_TOOLS
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
    if name == "super_memory_lifecycle_cache":
        return bridge.lifecycle_cache(action=args.get("action", "status"), config_path=args.get("config_path"))
    if name == "super_memory_lifecycle_tier":
        return bridge.lifecycle_tier(action=args.get("action", "evaluate"), dry_run=args.get("dry_run", True), limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_lifecycle_compression":
        return bridge.lifecycle_compression(action=args.get("action", "review"), dry_run=args.get("dry_run", True), limit=args.get("limit", 500), config_path=args.get("config_path"))
    if name == "super_memory_reflex_status":
        return bridge.reflex_status(config_path=args.get("config_path"))
    if name == "super_memory_train_local":
        return bridge.train_local(args["path"], domain_tag=args.get("domain_tag", "local"), recursive=args.get("recursive", True), limit=args.get("limit", 200), save=args.get("save", True), config_path=args.get("config_path"))
    if name == "super_memory_import_local":
        return bridge.import_local(args["path"], source_name=args.get("source_name", "local-import"), recursive=args.get("recursive", True), limit=args.get("limit", 200), save=args.get("save", True), config_path=args.get("config_path"))
    if name == "super_memory_watch_scan":
        return bridge.watch_scan(args["directory"], recursive=args.get("recursive", True), limit=args.get("limit", 200), save=args.get("save", False), config_path=args.get("config_path"))
    if name == "super_memory_sync_status":
        return bridge.sync_status(config_path=args.get("config_path"))
    if name == "super_memory_store_status":
        return bridge.store_status(config_path=args.get("config_path"))
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
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle(request)
        except Exception as exc:  # keep MCP transport alive and report as JSON-RPC error
            response = _error(None, -32000, str(exc), traceback.format_exc())
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
