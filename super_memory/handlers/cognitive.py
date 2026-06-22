"""Cognitive handlers — hypotheses, predictions, evidence, conflicts."""
from __future__ import annotations

from .. import bridge
from .base import ToolHandler, SimpleHandler
from .core import _str, _int, _num, _bool, _array, _obj, CFG


def get_cognitive_handlers() -> list[ToolHandler]:
    return [
        SimpleHandler(
            "super_memory_hypothesis_create",
            "Create a deterministic cognitive hypothesis.",
            bridge.hypothesis_create,
            properties={
                "content": _str("Hypothesis statement"),
                "confidence": _num("Initial confidence", 0.5),
                "tags": _array("Tags"),
                "config_path": CFG,
            },
            required=["content"],
        ),
        SimpleHandler(
            "super_memory_hypothesis_get",
            "Get hypothesis detail with evidence/predictions.",
            bridge.hypothesis_get,
            properties={"hypothesis_id": _str("Hypothesis ID"), "config_path": CFG},
            required=["hypothesis_id"],
        ),
        SimpleHandler(
            "super_memory_hypothesis_list",
            "List hypotheses.",
            bridge.hypothesis_list,
            properties={"status": _str("Filter by status"), "limit": _int("Max results", 20), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_evidence_add",
            "Add evidence for/against a hypothesis.",
            bridge.evidence_add,
            properties={
                "hypothesis_id": _str("Hypothesis ID"),
                "content": _str("Evidence content"),
                "direction": _str("for/against", "for"),
                "weight": _num("Evidence weight", 0.5),
                "config_path": CFG,
            },
            required=["hypothesis_id", "content"],
        ),
        SimpleHandler(
            "super_memory_prediction_create",
            "Create a falsifiable prediction.",
            bridge.prediction_create,
            properties={
                "content": _str("Prediction statement"),
                "confidence": _num("Confidence", 0.7),
                "hypothesis_id": _str("Linked hypothesis ID"),
                "deadline": _str("ISO deadline"),
                "config_path": CFG,
            },
            required=["content"],
        ),
        SimpleHandler(
            "super_memory_prediction_list",
            "List predictions.",
            bridge.prediction_list,
            properties={"status": _str("Filter by status"), "limit": _int("Max results", 20), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_verify_prediction",
            "Verify a prediction as correct/wrong.",
            bridge.verify_prediction,
            properties={
                "prediction_id": _str("Prediction ID"),
                "outcome": _str("correct or wrong"),
                "content": _str("Observation content"),
                "config_path": CFG,
            },
            required=["prediction_id", "outcome"],
        ),
        SimpleHandler(
            "super_memory_conflicts",
            "Detect/list deterministic conflict candidates.",
            bridge.conflicts,
            properties={"content": _str("Content to check"), "memory_id": _str("Memory ID"), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_detect_conflicts",
            "Detect conflicting memories via negation/temporal analysis.",
            bridge.detect_conflicts,
            properties={
                "content": _str("Content to check"),
                "min_similarity": _num("Min similarity", 0.3),
                "limit": _int("Max results", 50),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_resolve_conflict",
            "Resolve a detected conflict.",
            bridge.resolve_conflict,
            properties={
                "conflict_key": _str("Conflict key"),
                "resolution": _str("keep_both/keep_a/keep_b/supersede"),
                "reason": _str("Reason"),
                "config_path": CFG,
            },
            required=["conflict_key", "resolution"],
        ),
        SimpleHandler(
            "super_memory_conflict_resolve",
            "Record a Phase 6 conflict resolution event.",
            bridge.conflict_resolve,
            properties={
                "conflict_id": _str("Conflict ID"),
                "resolution": _str("Resolution"),
                "reason": _str("Reason"),
                "config_path": CFG,
            },
            required=["conflict_id", "resolution"],
        ),
        SimpleHandler(
            "super_memory_gaps",
            "Detect/record a knowledge gap event.",
            bridge.gaps,
            properties={
                "topic": _str("Knowledge gap topic"),
                "action": _str("detect/list/resolve/get", "detect"),
                "config_path": CFG,
            },
            required=["topic"],
        ),
        SimpleHandler(
            "super_memory_explain",
            "Explain relationship by merged recall path.",
            bridge.explain,
            properties={"from_entity": _str("Source entity"), "to_entity": _str("Target entity"), "config_path": CFG},
            required=["from_entity", "to_entity"],
        ),
        SimpleHandler(
            "super_memory_provenance",
            "Trace/verify/approve memory provenance.",
            bridge.provenance,
            properties={
                "memory_id": _str("Memory ID"),
                "action": _str("trace/verify/approve", "trace"),
                "actor": _str("Actor name", "super-memory"),
                "config_path": CFG,
            },
            required=["memory_id"],
        ),
        SimpleHandler(
            "super_memory_source",
            "Register an external source metadata record.",
            bridge.source,
            properties={
                "name": _str("Source name"),
                "source_type": _str("Source type"),
                "version": _str("Version"),
                "status": _str("Status"),
                "metadata": _obj("Additional metadata"),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_version",
            "Create/list lightweight memory version snapshots.",
            bridge.version,
            properties={
                "action": _str("create/list", "create"),
                "name": _str("Snapshot name", "snapshot"),
                "description": _str("Description"),
                "limit": _int("Max entries", 20),
                "config_path": CFG,
            },
        ),
        SimpleHandler(
            "super_memory_version_create",
            "Create a brain version snapshot for safe rollback.",
            bridge.version_create,
            properties={"name": _str("Snapshot name", "snapshot"), "description": _str("Description", ""), "config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_version_list",
            "List all version snapshots.",
            bridge.version_list,
            properties={"config_path": CFG},
        ),
        SimpleHandler(
            "super_memory_version_diff",
            "Diff two version snapshots.",
            bridge.version_diff,
            properties={"from_version": _str("Source version"), "to_version": _str("Target version"), "config_path": CFG},
            required=["from_version", "to_version"],
        ),
        SimpleHandler(
            "super_memory_version_rollback_dry_run",
            "Preview rollback to a snapshot (non-destructive).",
            bridge.version_rollback_dry_run,
            properties={"version_id": _str("Version ID"), "config_path": CFG},
            required=["version_id"],
        ),
    ]
