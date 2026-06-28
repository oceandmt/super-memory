from .fingerprint import Fingerprint, build_fingerprint, normalize_for_dedup, hamming_distance
from .idempotency import make_source_event_key
from .migrations import ensure_schema
from .outbox import register_memory, find_duplicate, job_status
from .worker import process_memory_jobs, reconcile_memory_integrity
from .semantic_merge import soft_delete_duplicate_clusters

__all__ = [
    "Fingerprint", "build_fingerprint", "normalize_for_dedup", "hamming_distance",
    "make_source_event_key", "ensure_schema", "register_memory", "find_duplicate",
    "job_status", "process_memory_jobs", "reconcile_memory_integrity", "soft_delete_duplicate_clusters",
]
