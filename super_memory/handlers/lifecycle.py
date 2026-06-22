"""Lifecycle & consolidation handlers — tier, lifecycle, consolidation, dreaming, maintenance."""
from __future__ import annotations

from .. import bridge
from .base import ToolHandler, SimpleHandler
from .core import _str, _int, _num, _bool, _array, _obj, CFG


def get_lifecycle_handlers() -> list[ToolHandler]:
    return [
        SimpleHandler(
            "super_memory_consolidate",
            "Record a safe non-destructive consolidation event.",
            bridge.consolidate,
            properties={"strategy": _str("Strategy", "all"), "dry_run": _bool("Preview only", True), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_consolidation_cycle",
            "Run a bounded deterministic Phase 6 consolidation report.",
            bridge.consolidation_cycle,
            properties={"strategy": _str("Strategy", "light"), "dry_run": _bool("Preview only", True), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_lifecycle_review",
            "Review lifecycle hygiene.",
            bridge.lifecycle_review,
            properties={"limit": _int("Max items", 500), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_lifecycle_quality_cleanup",
            "Soft-delete duplicates and mark long transcripts for compression.",
            bridge.lifecycle_quality_cleanup,
            properties={"dry_run": _bool("Preview only", True), "limit": _int("Max items", 500), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_lifecycle_cache",
            "Manage local activation cache status/save/load/clear.",
            bridge.lifecycle_cache,
            properties={"action": _str("status/save/load/clear", "status"), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_lifecycle_tier",
            "Evaluate/apply deterministic memory tiers.",
            bridge.lifecycle_tier,
            properties={"action": _str("evaluate/apply", "evaluate"), "dry_run": _bool("Preview only", True), "limit": _int("Max items", 500), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_lifecycle_compression",
            "Review/mark compression candidates without truncating content.",
            bridge.lifecycle_compression,
            properties={"action": _str("review", "review"), "dry_run": _bool("Preview only", True), "limit": _int("Max items", 500), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_pin",
            "Record pin/unpin intent for a memory.",
            bridge.pin,
            properties={"memory_id": _str("Memory ID"), "action": _str("pin/unpin", "pin"), "config_path": CFG},
            required=["memory_id"],
        ),
        SimpleHandler(
            "super_memory_reflex",
            "Record reflex pin/unpin intent for a memory.",
            bridge.reflex,
            properties={"memory_id": _str("Memory ID"), "action": _str("pin/unpin", "pin"), "config_path": CFG},
            required=["memory_id"],
        ),
        SimpleHandler(
            "super_memory_reflex_pin",
            "Pin a neuron as always-on reflex for boosted recall.",
            bridge.reflex_pin,
            properties={"neuron_id": _str("Neuron ID"), "content": _str("Content"), "config_path": CFG},
            required=["neuron_id"],
        ),
        SimpleHandler(
            "super_memory_reflex_unpin",
            "Unpin a neuron from reflex status.",
            bridge.reflex_unpin,
            properties={"neuron_id": _str("Neuron ID"), "config_path": CFG},
            required=["neuron_id"],
        ),
        SimpleHandler(
            "super_memory_reflex_list",
            "List all reflex-pinned neurons.",
            bridge.reflex_list,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_reflex_status",
            "Show reflex audit events and missing refs.",
            bridge.reflex_status,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_boundaries",
            "List or save domain boundary memory.",
            bridge.boundaries,
            properties={"domain": _str("Domain", "global"), "content": _str("Boundary content"), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_maintenance_run",
            "Run safe maintenance: cleanup, semantic index, short-term policy, dreaming, health checks.",
            bridge.maintenance_run,
            properties={"dry_run": _bool("Preview only", True), "limit": _int("Max items", 500), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_short_term_audit",
            "Audit short-term event memories for promotion candidates.",
            bridge.short_term_audit,
            properties={"limit": _int("Max items", 500), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_short_term_repair",
            "Promote high-signal short-term clusters and mark raw events for compression.",
            bridge.short_term_repair,
            properties={"dry_run": _bool("Preview only", True), "limit": _int("Max items", 500), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_short_term_mark_reviewed",
            "Mark a short-term promotion cluster as reviewed/promoted/deferred/ignored.",
            bridge.short_term_mark_reviewed,
            properties={"cluster_key": _str("Cluster key"), "decision": _str("reviewed/promoted/deferred/ignored", "deferred"), "config_path": CFG},
            required=["cluster_key"],
        ),
        SimpleHandler(
            "super_memory_dreaming_audit",
            "Audit inputs for dreaming/sleep consolidation artifacts.",
            bridge.dreaming_audit,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_dreaming_run",
            "Create a deterministic dreaming consolidation artifact and optional insight memory.",
            bridge.dreaming_run,
            properties={"dry_run": _bool("Preview only", True), "limit": _int("Max items", 200), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_dreaming_repair",
            "Inspect dreaming artifacts and recommend non-destructive repair/run actions.",
            bridge.dreaming_repair,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_feedback_outcome",
            "Record task/memory outcome feedback for learning.",
            bridge.feedback_outcome,
            properties={"memory_id": _str("Memory ID"), "success": _bool("Success", True), "outcome": _str("Outcome description"), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_expire_by_age",
            "Soft-delete memories past their expires_days TTL.",
            bridge.expire_by_age,
            properties={"dry_run": _bool("Preview only", True), "max_days": _int("Max days", 90), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_expire_by_valid_until",
            "Soft-delete memories past their valid_until window.",
            bridge.expire_by_valid_until,
            properties={"dry_run": _bool("Preview only", True), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_auto_compact",
            "Auto-compact soft-deleted records when ratio exceeds threshold.",
            bridge.auto_compact,
            properties={"threshold": _num("Threshold", 0.2), "dry_run": _bool("Preview only", True), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_cleanup",
            "Safe SQLite cleanup: migrations, derived views, FTS rebuilds.",
            bridge.cleanup,
            properties={"config_path": CFG, "vacuum": _bool("Run VACUUM", False), "integrity_check": _bool("Run integrity check", True)},
        ),
        SimpleHandler(
            "super_memory_promotion_candidates",
            "List deterministic promotion candidates.",
            bridge.promotion_candidates,
            properties={"limit": _int("Max results", 20), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_write_queue_flush",
            "Flush the deferred write queue.",
            bridge.write_queue_flush,
            properties={"queue_key": _str("Queue key", "default"), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_write_queue_defer",
            "Defer a memory record to the write queue for batch flush.",
            bridge.write_queue_defer,
            properties={
                "content": _str("Memory content"),
                "type_": _str("Memory type", "context"),
                "scope": _str("Scope", "session"),
                "agent_id": _str("Agent ID", "lucas"),
                "tags": _array("Tags"),
                "config_path": CFG,
            },
            required=["content"],
        ),
        SimpleHandler(
            "super_memory_prune",
            "Prune memories matching retention policy criteria.",
            bridge.prune,
            properties={
                "dry_run": _bool("Preview only", True),
                "source_prefixes": _array("Source prefixes to filter"),
                "max_days": _int("Max age in days"),
                "config_path": CFG,
            },
        ),
    ]
