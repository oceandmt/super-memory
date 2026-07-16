"""Canonical identity and revision contract for derived projections.

Canonical memory content is authoritative.  Projection stores may cache a
``content_hash`` for diagnostics, but revisions are always recomputed from the
actual canonical content so a stale cached hash cannot make a projection look
current.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

CANONICAL_CONTRACT_VERSION = "1"
DEFAULT_CANONICAL_LAYER = "workspace_markdown"


def content_hash(content: str) -> str:
    """Return the lowercase SHA-256 hex digest of canonical UTF-8 content."""
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def canonical_id(memory_id: str, layer: str = DEFAULT_CANONICAL_LAYER) -> str:
    """Return an unambiguous, stable identity for one canonical memory row."""
    memory_id = str(memory_id or "")
    layer = str(layer or DEFAULT_CANONICAL_LAYER)
    if not memory_id:
        raise ValueError("memory_id must not be empty")
    # Length-prefixing avoids ambiguity without depending on URL escaping rules.
    return f"memory:v{CANONICAL_CONTRACT_VERSION}:{len(layer)}:{layer}:{memory_id}"


def source_revision(source_hash: str) -> str:
    """Return the canonical revision token for a SHA-256 source hash."""
    digest = str(source_hash or "").lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("source_hash must be a SHA-256 hex digest")
    return f"sha256:{digest}"


@dataclass(frozen=True)
class CanonicalRevision:
    """Identity and content-derived revision of one canonical memory row."""

    memory_id: str
    layer: str
    canonical_id: str
    source_hash: str
    source_revision: str
    contract_version: str = CANONICAL_CONTRACT_VERSION

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def canonical_revision(
    memory_id: str,
    content: str,
    layer: str = DEFAULT_CANONICAL_LAYER,
) -> CanonicalRevision:
    """Build the canonical contract from identity, layer, and actual content."""
    layer = str(layer or DEFAULT_CANONICAL_LAYER)
    digest = content_hash(content)
    return CanonicalRevision(
        memory_id=str(memory_id),
        layer=layer,
        canonical_id=canonical_id(memory_id, layer),
        source_hash=digest,
        source_revision=source_revision(digest),
    )


def projection_id(
    revision: CanonicalRevision,
    projection_type: str,
    adapter_name: str,
    adapter_version: str,
) -> str:
    """Return a stable projection identity independent of source revision.

    A projection row represents one adapter/type slot for one canonical row.
    When canonical content changes, the same row becomes stale and can later be
    replaced by a projection of the new revision without accumulating multiple
    rows that all claim to be active.
    """
    payload: dict[str, Any] = {
        "adapter_name": str(adapter_name),
        "adapter_version": str(adapter_version),
        "canonical_id": revision.canonical_id,
        "contract_version": CANONICAL_CONTRACT_VERSION,
        "projection_type": str(projection_type),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "projection:v1:" + hashlib.sha256(encoded).hexdigest()
