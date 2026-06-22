"""SimHash near-duplicate detection for Super Memory.

Ported from neural-memory v4.58.0 utils/simhash.py.
Uses fingerprint-based Hamming distance to detect near-duplicate
content at memory save time, reducing duplicate cluster accumulation.

Algorithm:
1. Tokenize text into shingles (char n-grams + word tokens)
2. Hash each shingle to a 64-bit fingerprint
3. Accumulate weighted bits (term frequency weighting)
4. Final fingerprint = sign of accumulated bits
5. Hamming distance < threshold → near-duplicate
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

logger = logging.getLogger("super-memory.simhash")

# Default threshold for near-duplicate detection
# Hamming distance < SIMHASH_THRESHOLD → considered near-duplicate
SIMHASH_THRESHOLD = 3


def _hash_fingerprint(text: str) -> int:
    """Compute a 64-bit MD5-based hash fingerprint."""
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:16], 16)


def _shingles(text: str, shingle_size: int = 3) -> list[str]:
    """Extract character n-gram shingles from text."""
    text = text.lower()
    shingles = []
    for i in range(len(text) - shingle_size + 1):
        shingles.append(text[i:i + shingle_size])
    return shingles


def compute_simhash(text: str) -> int:
    """Compute SimHash fingerprint for text.

    Uses character trigrams as features with TF weighting.
    Returns a 64-bit integer fingerprint.
    """
    if not text:
        return 0

    # Word tokens for TF weighting
    words = re.findall(r"\w+", text.lower())
    word_counts: dict[str, int] = {}
    for w in words:
        word_counts[w] = word_counts.get(w, 0) + 1

    # Shingles for fingerprint (character n-grams)
    shingles_list = _shingles(text, shingle_size=3)

    # Accumulate weighted bits
    bits = [0] * 64

    for shingle in set(shingles_list):
        hash_val = _hash_fingerprint(shingle)

        # Weight = sum of TF for words that overlap with this shingle
        weight = 1.0
        for word, count in word_counts.items():
            if word in shingle:
                weight += count * 0.5

        for i in range(64):
            if hash_val & (1 << i):
                bits[i] += weight
            else:
                bits[i] -= weight

    # Final fingerprint
    fingerprint = 0
    for i in range(64):
        if bits[i] > 0:
            fingerprint |= 1 << i

    return fingerprint


def hamming_distance(hash_a: int, hash_b: int) -> int:
    """Compute Hamming distance between two SimHash fingerprints."""
    xor_val = hash_a ^ hash_b
    # Popcount using bit manipulation
    distance = 0
    while xor_val:
        distance += xor_val & 1
        xor_val >>= 1
    return distance


def is_near_duplicate(hash_a: int, hash_b: int, threshold: int = SIMHASH_THRESHOLD) -> bool:
    """Check if two fingerprints are near-duplicates."""
    if hash_a == 0 or hash_b == 0:
        return False
    return hamming_distance(hash_a, hash_b) <= threshold


def compute_content_hash(text: str) -> int:
    """Compute a content-based SimHash for dedup checking.

    Normalizes text before fingerprinting (lowercase, strip whitespace,
    remove common noise).
    """
    if not text:
        return 0

    # Normalize
    normalized = text.lower().strip()
    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized)
    # Remove extremely short fragments (single chars)
    normalized = re.sub(r"\b\w\b", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return compute_simhash(normalized)


class SimHashIndex:
    """In-memory SimHash index for batch near-dup detection.

    Stores fingerprints and provides lookup for near-duplicates
    against a query fingerprint.
    """

    def __init__(self, threshold: int = SIMHASH_THRESHOLD) -> None:
        self._threshold = threshold
        self._fingerprints: dict[str, int] = {}  # memory_id → fingerprint
        self._reverse: dict[int, list[str]] = {}  # fingerprint → [memory_ids]

    def add(self, memory_id: str, fingerprint: int) -> None:
        """Add a fingerprint to the index."""
        self._fingerprints[memory_id] = fingerprint
        self._reverse.setdefault(fingerprint, []).append(memory_id)

    def find_near_duplicates(self, fingerprint: int) -> list[str]:
        """Find memory IDs that are near-duplicates of the given fingerprint."""
        if fingerprint == 0:
            return []

        matches: list[str] = []
        for existing_fp, mem_ids in self._reverse.items():
            if is_near_duplicate(fingerprint, existing_fp, self._threshold):
                matches.extend(mem_ids)
        return matches

    def find_for_text(self, text: str) -> list[str]:
        """Compute fingerprint from text and find near-duplicates."""
        fp = compute_content_hash(text)
        return self.find_near_duplicates(fp)

    def clear(self) -> None:
        """Clear the index."""
        self._fingerprints.clear()
        self._reverse.clear()


# ── Integration helper ────────────────────────────────────────────────────────

def simhash_dedup_check(
    content: str,
    existing_fingerprints: dict[str, int] | None = None,
    threshold: int = SIMHASH_THRESHOLD,
) -> dict[str, Any]:
    """Check if content is near-duplicate of existing fingerprints.

    Returns:
        {
            "is_dup": bool,
            "matched_id": str | None,
            "hamming_distance": int,
            "fingerprint": int,
        }
    """
    if not content or not existing_fingerprints:
        return {"is_dup": False, "matched_id": None, "hamming_distance": 0, "fingerprint": 0}

    query_fp = compute_content_hash(content)
    min_dist = threshold + 1
    best_match = None

    for mem_id, fp in existing_fingerprints.items():
        dist = hamming_distance(query_fp, fp)
        if dist < min_dist:
            min_dist = dist
            best_match = mem_id

    is_dup = min_dist <= threshold
    return {
        "is_dup": is_dup,
        "matched_id": best_match if is_dup else None,
        "hamming_distance": min_dist,
        "fingerprint": query_fp,
    }
