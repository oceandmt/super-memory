"""3-tier dedup pipeline: SimHash → Embedding → LLM.

Ported from neural-memory v4.58.0 engine/dedup/pipeline.py.
Synchronous version adapted for super-memory's non-async storage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from .config import DedupConfig

logger = logging.getLogger("super-memory.dedup")


@dataclass(frozen=True)
class DedupResult:
    is_duplicate: bool
    existing_neuron_id: str = ""
    tier: int = 0
    similarity_score: float = 0.0
    reason: str = ""


class DedupPipeline:
    """3-tier dedup: SimHash (T1) → Embedding cosine (T2) → LLM judge (T3)."""

    def __init__(
        self,
        config: DedupConfig,
        store: Any,
        vector_store: Any | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._vector_store = vector_store

    def check_duplicate(
        self,
        content: str,
        content_hash: int | None = None,
    ) -> DedupResult:
        """Check if content duplicates an existing memory."""
        if not self._config.enabled:
            return DedupResult(False, reason="dedup disabled")
        if not content or not content.strip():
            return DedupResult(False, reason="empty content")

        if content_hash is None:
            from ..simhash import compute_content_hash
            content_hash = compute_content_hash(content)

        # Tier 1: SimHash
        hash_candidates = self._get_candidates_by_hash(content_hash)
        if hash_candidates:
            t1 = self._tier1_simhash(content_hash, hash_candidates)
            if t1 is not None:
                return t1

        # Fetch content-based candidates
        candidates = self._get_candidates(content)
        if not candidates:
            return DedupResult(False, reason="no candidates")

        # Tier 1: SimHash on all candidates
        t1 = self._tier1_simhash(content_hash, candidates)
        if t1 is not None:
            return t1

        # Tier 2: Embedding cosine
        if self._vector_store is not None:
            t2 = self._tier2_embedding(content, candidates)
            if t2 is not None:
                return t2

        return DedupResult(False, reason="no tier found match")

    def _get_candidates_by_hash(self, content_hash: int) -> list[dict]:
        """Fast path: fetch candidates by exact content_hash."""
        if content_hash == 0:
            return []
        try:
            with self._store.connect() as conn:
                rows = conn.execute(
                    "SELECT id, content, metadata_json FROM memories "
                    "WHERE json_extract(metadata_json, '$.simhash_fingerprint') = ? "
                    "AND (json_extract(metadata_json, '$.soft_deleted') IS NULL "
                    "OR json_extract(metadata_json, '$.soft_deleted') != 1) "
                    "LIMIT 10",
                    (str(content_hash),),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _get_candidates(self, content: str) -> list[dict]:
        """Fetch candidate memories for comparison."""
        max_candidates = min(self._config.max_candidates, 50)
        words = content.split()
        search_term = ""
        for word in words:
            cleaned = word.strip(".,;:!?\"'()[]{}").lower()
            if len(cleaned) >= 3:
                search_term = cleaned
                break
        if not search_term:
            return []
        try:
            with self._store.connect() as conn:
                rows = conn.execute(
                    "SELECT id, content, metadata_json FROM memories "
                    "WHERE content LIKE ? "
                    "AND (json_extract(metadata_json, '$.soft_deleted') IS NULL "
                    "OR json_extract(metadata_json, '$.soft_deleted') != 1) "
                    "ORDER BY rowid DESC LIMIT ?",
                    (f"%{search_term}%", max_candidates),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _tier1_simhash(self, content_hash: int, candidates: list[dict]) -> DedupResult | None:
        from ..simhash import hamming_distance
        threshold = self._config.simhash_threshold
        for row in candidates:
            meta = json.loads(row.get("metadata_json", "{}"))
            existing_fp = meta.get("simhash_fingerprint", 0)
            if existing_fp:
                try:
                    existing_fp = int(existing_fp)
                except (ValueError, TypeError):
                    continue
                dist = hamming_distance(content_hash, existing_fp)
                if dist <= threshold:
                    similarity = 1.0 - (dist / 64.0)
                    return DedupResult(True, row["id"], 1, similarity, f"SimHash dist={dist}")
        return None

    def _tier2_embedding(self, content: str, candidates: list[dict]) -> DedupResult | None:
        if self._vector_store is None:
            return None
        try:
            # Use vector store search to find similar content
            semantic_results = self._vector_store.search_text(content, top_k=5)
            if not semantic_results:
                return None
            best_id, best_score = semantic_results[0]
            if best_score >= self._config.embedding_threshold:
                return DedupResult(True, best_id, 2, best_score, f"Embedding score={best_score:.3f}")
            if best_score < self._config.embedding_ambiguous_low:
                return DedupResult(False, tier=2, similarity_score=best_score, reason=f"Embedding mismatch {best_score:.3f}")
            return None  # borderline — defer to LLM if available
        except Exception:
            return None


# Prompt templates for optional LLM-based dedup (Tier 3)
DEDUP_SYSTEM_PROMPT = """\
You are a deduplication judge. Determine if two memory entries are semantically
equivalent (duplicates) or distinct memories. Respond with EXACTLY one of:
- DUPLICATE: Same core information
- DISTINCT: Meaningfully different information
- UNCERTAIN: Cannot confidently determine
Follow with a brief reason on the next line."""

DEDUP_USER_PROMPT = """\
Memory A:
{content_a}
Memory B:
{content_b}
Are these duplicates or distinct? Consider:
1. Do they convey the same core fact/decision/instruction?
2. Is one a more specific version of the other?
3. Would keeping both add redundant information?"""
