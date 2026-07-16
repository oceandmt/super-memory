from .fingerprint import Fingerprint, build_fingerprint, hamming_distance, normalize_for_dedup
from .idempotency import (
    claim_write_intent,
    make_source_event_key,
    mark_write_intent_failed,
    mark_write_intent_saved,
)
from .migrations import ensure_schema
from .outbox import find_duplicate, job_status, register_memory
from .semantic_merge import soft_delete_duplicate_clusters
from .worker import process_memory_jobs, reconcile_memory_integrity

__all__ = [
    "Fingerprint", "build_fingerprint", "normalize_for_dedup", "hamming_distance",
    "make_source_event_key", "claim_write_intent", "mark_write_intent_saved",
    "mark_write_intent_failed", "ensure_schema", "register_memory", "find_duplicate",
    "job_status", "process_memory_jobs", "reconcile_memory_integrity", "soft_delete_duplicate_clusters",
]
