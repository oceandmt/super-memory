"""Core CRUD handlers — remember, recall, show, context, todo, auto, etc."""
from __future__ import annotations

from typing import Any

from .. import bridge
from .base import ToolHandler, SimpleHandler


# ── Tool Property Helpers ────────────────────────────────────────────────────

def _array(desc: str, items: dict | None = None) -> dict:
    return {"type": "array", "description": desc, **(items or {"items": {"type": "string"}})}

def _str(desc: str, default: str = "") -> dict:
    r: dict = {"type": "string", "description": desc}
    if default:
        r["default"] = default
    return r

def _int(desc: str, default: int = 0) -> dict:
    return {"type": "integer", "description": desc, "default": default}

def _num(desc: str, default: float = 0.0) -> dict:
    return {"type": "number", "description": desc, "default": default}

def _bool(desc: str, default: bool = False) -> dict:
    return {"type": "boolean", "description": desc, "default": default}

def _obj(desc: str) -> dict:
    return {"type": "object", "description": desc}

CFG = {"type": "string", "description": "Config path override"}


# ── All core CRUD handlers ───────────────────────────────────────────────────

def get_core_handlers() -> list[ToolHandler]:
    return [
        SimpleHandler(
            "super_memory_remember",
            "Save a memory through Super Memory canonical-first layer order.",
            bridge.remember,
            properties={
                "content": _str("Memory content"),
                "type": _str("Memory type", "context"),
                "scope": _str("Scope", "session"),
                "agent_id": _str("Agent ID", "lucas"),
                "session_id": _str("Session ID"),
                "project": _str("Project name"),
                "tags": _array("Tags for categorization"),
                "source": _str("Source identifier"),
                "trust_score": _num("Trust score 0-1"),
                "metadata": _obj("Additional metadata"),
                "defer": _bool("Queue for batch flush", False),
                "config_path": CFG,
            },
            required=["content"],
        ),
        SimpleHandler(
            "super_memory_remember_batch",
            "Save multiple memories through the same canonical-first layer order; partial failures stay per item.",
            bridge.remember_batch,
            properties={
                "memories": {"type": "array", "items": {"type": "object"}, "maxItems": 20, "description": "Array of memories"},
                "config_path": CFG,
            },
            required=["memories"],
        ),
        SimpleHandler(
            "super_memory_show",
            "Show a memory by id across derived Super Memory layers.",
            bridge.show,
            properties={"memory_id": _str("Memory ID"), "config_path": CFG},
            required=["memory_id"],
        ),
        SimpleHandler(
            "super_memory_context",
            "Get recent or query-relevant Super Memory context.",
            bridge.context,
            properties={
                "query": _str("Optional query filter", ""),
                "limit": _int("Max results", 10),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_todo",
            "Save a TODO memory through canonical-first layer order.",
            bridge.todo,
            properties={"task": _str("Task description"), "priority": _int("Priority 0-10", 5), "config_path": CFG},
            required=["task"],
        ),
        SimpleHandler(
            "super_memory_auto",
            "Extract simple memory candidates from text and optionally save them canonical-first.",
            bridge.auto,
            properties={"text": _str("Text to analyze"), "save": _bool("Save extracted memories", False), "config_path": CFG},
            required=["text"],
        ),
        SimpleHandler(
            "super_memory_stats",
            "Show memory statistics.",
            bridge.stats,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_status",
            "Show Super Memory local service status.",
            bridge.status,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_health",
            "Check Super Memory consistency guardrails.",
            bridge.health,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_situation",
            "Return current memory situation summary.",
            bridge.situation,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_promote",
            "Promote a memory to MEMORY.md and the matching register.",
            bridge.promote,
            properties={"memory_id": _str("Memory ID"), "config_path": CFG},
            required=["memory_id"],
            admin_only=True,
        ),
        SimpleHandler(
            "super_memory_forget",
            "Delete a memory (soft by default).",
            bridge.forget,
            properties={"memory_id": _str("Memory ID"), "hard": _bool("Permanent deletion", False), "reason": _str("Why forgotten"), "config_path": CFG},
            required=["memory_id"],
        ),
        SimpleHandler(
            "super_memory_edit",
            "Edit a memory's content, type, priority, or tier.",
            bridge.edit,
            properties={
                "memory_id": _str("Memory ID"),
                "content": _str("New content"),
                "type": _str("New type"),
                "priority": _int("New priority", 5),
                "tier": _str("New tier (hot/warm/cold)"),
                "config_path": CFG,
            },
            required=["memory_id"],
        ),
        SimpleHandler(
            "super_memory_quality_score",
            "Run quality assessment on memory content.",
            bridge.quality_score,
            properties={"content": _str("Memory content"), "memory_type": _str("Memory type", "context"), "config_path": CFG},
            required=["content"],
        ),
        SimpleHandler(
            "super_memory_sync_turn",
            "Save a compact multi-agent conversation turn event.",
            bridge.sync_turn,
            properties={
                "agent_id": _str("Agent ID", "lucas"),
                "session_id": _str("Session ID"),
                "user_message": _str("User message"),
                "assistant_message": _str("Assistant message"),
                "project": _str("Project name"),
                "metadata": _obj("Additional metadata"),
                "config_path": CFG,
            },
        ),
    ]


def get_recall_handlers() -> list[ToolHandler]:
    """Recall/prefetch/search handlers."""
    return [
        SimpleHandler(
            "super_memory_recall",
            "Recall memories from Super Memory layers.",
            bridge.recall,
            properties={"query": _str("Search query"), "limit": _int("Max results", 10), "config_path": CFG},
            required=["query"],
        ),
        SimpleHandler(
            "super_memory_prefetch",
            "Merged/deduped Super Memory recall for prompt prefetch.",
            bridge.prefetch,
            properties={"query": _str("Search query"), "limit": _int("Max results", 10), "config_path": CFG},
            required=["query"],
        ),
        SimpleHandler(
            "super_memory_memory_search",
            "OpenClaw memory_search-compatible recall payload.",
            bridge.memory_search,
            properties={
                "query": _str("Search query"),
                "max_results": _int("Max results", 5),
                "min_score": _num("Min score", 0.0),
                "corpus": _str("Corpus filter", "all"),
                "config_path": CFG,
            },
            required=["query"],
        ),
        SimpleHandler(
            "super_memory_memory_get",
            "OpenClaw memory_get-compatible read.",
            bridge.memory_get,
            properties={
                "path": _str("Path"),
                "from_line": _int("Start line", 1),
                "lines": _int("Line count", 20),
                "corpus": _str("Corpus filter", "all"),
                "config_path": CFG,
            },
            required=["path"],
        ),
        SimpleHandler(
            "super_memory_recall_arbitrate",
            "Recall from layers and explain layer arbitration.",
            bridge.recall_arbitrate,
            properties={"query": _str("Search query"), "limit": _int("Max results", 10), "config_path": CFG},
        ),
    ]


def get_working_memory_handlers() -> list[ToolHandler]:
    """Working memory + routing handlers."""
    return [
        SimpleHandler(
            "super_memory_working_memory_get",
            "Get Phase 6 short-lived working memory state.",
            bridge.working_memory_get,
            properties={"key": _str("Key", "default"), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_working_memory_set",
            "Set/merge Phase 6 short-lived working memory state.",
            bridge.working_memory_set,
            properties={
                "payload": _obj("State payload"),
                "key": _str("Key", "default"),
                "ttl_seconds": _int("TTL in seconds"),
                "config_path": CFG,
            },
            required=["payload"],
        ),
        SimpleHandler(
            "super_memory_attention_score",
            "Score memory salience and routing signals.",
            bridge.attention_score,
            properties={"payload": _obj("Input payload"), "config_path": CFG},
            required=["payload"],
        ),
        SimpleHandler(
            "super_memory_route_memory",
            "Route a memory payload using deterministic Phase 6 attention policy.",
            bridge.route_memory,
            properties={"payload": _obj("Memory payload"), "config_path": CFG},
            required=["payload"],
        ),
        SimpleHandler(
            "super_memory_parallel_save",
            "Run Phase 6 working-memory plus canonical-first save/projection flow.",
            bridge.parallel_save,
            properties={"payload": _obj("Save payload"), "config_path": CFG},
            required=["payload"],
        ),
    ]


def get_search_index_handlers() -> list[ToolHandler]:
    """Semantic index and embedding handlers."""
    return [
        SimpleHandler(
            "super_memory_semantic_index",
            "Incrementally index canonical workspace memories into sqlite-vec.",
            bridge.semantic_index,
            properties={
                "rebuild": _bool("Full rebuild", False),
                "batch_size": _int("Batch size", 8),
                "limit": _int("Max items"),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_semantic_verify",
            "Verify semantic KNN recall and hydrate canonical memories.",
            bridge.semantic_verify,
            properties={
                "query": _str("Test query", "semantic recall smoke test"),
                "limit": _int("Max results", 5),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_semantic_doctor",
            "Run semantic sqlite-vec/Ollama doctor checks.",
            bridge.semantic_doctor,
            properties={
                "query": _str("Test query", "semantic recall smoke test"),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_semantic_quality_audit",
            "Check known durable queries rank high in semantic retrieval.",
            bridge.semantic_quality_audit,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_embedding_doctor",
            "Inspect embedding/semantic provider health.",
            bridge.embedding_doctor,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_embedding_auto_select",
            "Choose the healthiest local recall backend.",
            bridge.embedding_auto_select,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_select_warm_activations",
            "Select warm activations ranked by embedding similarity.",
            bridge.select_warm_activations,
            properties={
                "query": _str("Query for embedding"),
                "top_k": _int("Top K", 20),
                "min_similarity": _num("Min similarity", 0.3),
                "config_path": CFG,
            },
        ),
    ]


def get_sanitize_handlers() -> list[ToolHandler]:
    """Sanitize/normalize helpers."""
    return [
        SimpleHandler(
            "super_memory_sanitize_prompt",
            "Sanitize recall/prompt text by redacting common secrets.",
            bridge.sanitize_prompt,
            properties={"text": _str("Text to sanitize")},
            required=["text"],
        ),
        SimpleHandler(
            "super_memory_sanitize_auto_capture",
            "Sanitize text before auto-capture storage.",
            bridge.sanitize_auto_capture,
            properties={"text": _str("Text to sanitize")},
            required=["text"],
        ),
        SimpleHandler(
            "super_memory_normalize_memory",
            "Normalize a memory payload schema without saving it.",
            bridge.normalize_memory_payload,
            properties={"memory": _obj("Memory payload"), "auto_capture": _bool("Auto-capture mode", False)},
            required=["memory"],
        ),
    ]
