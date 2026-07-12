"""MemoryEnvelope v1 — canonical contract for every memory.

Borrows from:
- Neural Memory: quality gate, trust scoring, typed memory model (TypedMemory)
- Honcho: provenance chain (source_ids), perspective (observer/observed)
- MemPalace: transformation manifest (declared_transformations, adapter_version)

Every memory that enters Super Memory should first be wrapped in a MemoryEnvelope
before canonical save, ensuring quality/trust/provenance/lifecycle metadata
exists uniformly across all layers (workspace_markdown, SQLite, graph, palace, events).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ── Canonical Type Taxonomy ──────────────────────────────────────────────────

class MemoryType(str, Enum):
    """Unified memory type taxonomy — covers all projected layers."""
    FACT = "fact"
    DECISION = "decision"
    PREFERENCE = "preference"
    TODO = "todo"
    BLOCKER = "blocker"
    WORKFLOW = "workflow"
    INSIGHT = "insight"
    CONTEXT = "context"
    DOCTRINE = "doctrine"
    LESSON = "lesson"
    EVENT = "event"
    INSTRUCTION = "instruction"
    REFERENCE = "reference"
    HYPOTHESIS = "hypothesis"
    PREDICTION = "prediction"
    SCHEMA = "schema"
    BOUNDARY = "boundary"


class MemoryScope(str, Enum):
    SESSION = "session"
    AGENT_LOCAL = "agent-local"
    SHARED = "shared"
    PROJECT = "project"
    CROSS_AGENT = "cross-agent"


class ObservationLevel(str, Enum):
    """Borrowed from Honcho: how a memory was derived."""
    EXPLICIT = "explicit"          # directly stated
    DEDUCTIVE = "deductive"        # derived from reasoning
    INDUCTIVE = "inductive"        # pattern inferred across sessions
    CONTRADICTION = "contradiction" # conflicts with existing knowledge


# ── Provenance ───────────────────────────────────────────────────────────────

@dataclass
class ProvenanceEntry:
    """Single hop in the provenance chain."""
    source_adapter: str            # e.g. "chat", "file", "url", "tool"
    adapter_version: str | None = None
    source_id: str | None = None   # deterministic content-based ID
    transformation: str | None = None  # "verbatim", "summarized", "extracted", "translated"
    confidence: float = 1.0
    timestamp: str | None = None
    actor: str | None = None       # which agent/user observed this


@dataclass
class ProvenanceChain:
    """Chain of custody — how this memory reached Super Memory."""
    entries: list[ProvenanceEntry] = field(default_factory=list)
    first_seen: str | None = None
    last_verified: str | None = None

    def add(self, entry: ProvenanceEntry) -> None:
        self.entries.append(entry)

    def source_type(self) -> str:
        if not self.entries:
            return "unknown"
        return self.entries[0].source_adapter

    def is_verbatim(self) -> bool:
        return all(e.transformation in (None, "verbatim") for e in self.entries)


# ── Lifecycle Policy ─────────────────────────────────────────────────────────

@dataclass
class LifecyclePolicy:
    """Lifecycle rules for this memory — decides decay, tier, expiration.

    Borrowed from Neural Memory lifecycle tiers (HOT/WARM/COLD) + expiration.
    """
    tier: str = "warm"             # hot / warm / cold
    decay_days: int | None = None  # None = use default by type
    expires_at: str | None = None  # ISO datetime or None
    auto_pin: bool = False         # skip decay/compr/expire
    review_after_days: int | None = None  # Leitner/spaced repetition
    type_decay_defaults = {
        "decision": 365,
        "fact": 180,
        "instruction": 180,
        "workflow": 90,
        "reference": 90,
        "insight": 60,
        "preference": 60,
        "todo": 30,
        "blocker": 30,
        "event": 7,
        "context": 14,
    }

    def effective_decay_days(self, memory_type: str = "context") -> int:
        if self.decay_days is not None:
            return self.decay_days
        return self.type_decay_defaults.get(memory_type, 30)

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > expiry
        except Exception:
            return False


# ── Transformation Manifest ──────────────────────────────────────────────────

@dataclass
class Transformation:
    """Borrowed from MemPalace: declared transformation applied to source content."""
    name: str                          # e.g. "chunk", "summarize", "extract-entities"
    version: str = "1.0"
    params: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        if self.params:
            return f"{self.name} v{self.version} ({json.dumps(self.params, sort_keys=True)})"
        return f"{self.name} v{self.version}"


# ── Projection Status ────────────────────────────────────────────────────────

@dataclass
class ProjectionStatus:
    """Tracks which derived layers this memory has been projected to."""
    workspace_markdown: bool = False
    sqlite: bool = False
    graph: bool = False
    palace: bool = False
    honcho_events: bool = False
    semantic_index: bool = False
    closets: bool = False
    custom: dict[str, bool] = field(default_factory=dict)

    def all_done(self, required: set[str] | None = None) -> bool:
        targets = required or {"workspace_markdown", "sqlite", "graph"}
        for t in targets:
            if not getattr(self, t, False):
                return False
        return True

    def missing(self) -> list[str]:
        return [k for k in self.__dataclass_fields__ if isinstance(getattr(self, k), bool) and not getattr(self, k)]


# ── MemoryEnvelope v1 ────────────────────────────────────────────────────────

@dataclass
class MemoryEnvelope:
    """Universal memory contract — wraps every canonical memory.

    All fields are populated during ingest and carried forward to every
    derived layer (workspace_markdown, SQLite, graph, palace, honcho events).

    P0 contract: quality_score, trust_score, provenance, lifecycle_policy,
    projection_status, transformation_manifest.
    """
    # Core identity
    id: str
    content: str
    content_hash: str = ""
    normalized_content: str = ""

    # Canonical taxonomy
    type: MemoryType = MemoryType.CONTEXT
    scope: MemoryScope = MemoryScope.SESSION

    # Agent/session context
    agent_id: str = "lucas"
    session_id: str | None = None
    project: str | None = None
    tags: list[str] = field(default_factory=list)

    # Quality & trust (P0)
    quality_score: float = 0.5
    trust_score: float | None = None
    confidence_score: float = 0.5

    # Provenance (P0 — borrowed from Honcho + MemPalace)
    provenance: ProvenanceChain = field(default_factory=ProvenanceChain)

    # Source adapter info (P0 — borrowed from MemPalace BaseSourceAdapter)
    source_adapter: str = "direct"    # e.g. "chat", "file", "url", "tool"
    source_id: str | None = None      # deterministic source content ID
    transformation_manifest: list[Transformation] = field(default_factory=list)

    # Lifecycle (P0 — borrowed from Neural Memory lifecycle tiers)
    lifecycle_policy: LifecyclePolicy = field(default_factory=LifecyclePolicy)

    # Observation level (borrowed from Honcho)
    observation_level: ObservationLevel = ObservationLevel.EXPLICIT

    # Links (borrowed from Honcho source_ids)
    source_ids: list[str] = field(default_factory=list)  # IDs of source memories
    supersedes_id: str | None = None   # ID of superseded memory
    superseded_by_id: str | None = None

    # Layer projection tracking (P0)
    projection_status: ProjectionStatus = field(default_factory=ProjectionStatus)

    # Embedding refs
    embedding_refs: list[str] = field(default_factory=list)

    # Raw metadata for extension
    metadata: dict[str, Any] = field(default_factory=dict)

    # Temporal
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()
        if self.normalized_content and not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()

    @property
    def effective_trust(self) -> float:
        """Combined trust: provenance confidence × quality × base trust."""
        base = self.trust_score if self.trust_score is not None else 0.5
        prov_conf = min((e.confidence for e in self.provenance.entries), default=1.0)
        return round(base * self.quality_score * prov_conf, 4)

    def to_memory_record(self) -> dict[str, Any]:
        """Convert to MemoryRecord-compatible dict for bridge.remember()."""
        return {
            "id": self.id,
            "content": self.content,
            "type": self.type.value,
            "scope": self.scope.value,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "project": self.project,
            "tags": self.tags,
            "source": self.source_adapter,
            "trust_score": self.effective_trust,
            "metadata": {
                "envelope_version": "1.0",
                "quality_score": self.quality_score,
                "confidence_score": self.confidence_score,
                "observation_level": self.observation_level.value,
                "provenance": [asdict(e) for e in self.provenance.entries],
                "transformations": [asdict(t) for t in self.transformation_manifest],
                "lifecycle_policy": asdict(self.lifecycle_policy),
                "source_ids": self.source_ids,
                "supersedes_id": self.supersedes_id,
                "superseded_by_id": self.superseded_by_id,
                "content_hash": self.content_hash,
            },
        }


# ── Trust Defaults ──────────────────────────────────────────────────────────

# Default trust_score by source_adapter when the caller does not supply one.
# Higher trust = more deliberate/verified input (direct human chat, explicit
# decision capture). Lower trust = automated/inferred capture (auto-extraction,
# raw event logging, unverified external URLs).
DEFAULT_TRUST_BY_SOURCE: dict[str, float] = {
    "chat": 0.75,          # direct human chat turn
    "direct": 0.6,         # explicit remember() call, no adapter context
    "file": 0.6,           # ingested from a local file
    "tool": 0.5,           # tool-call output
    "url": 0.4,            # external web content, unverified
    "super-memory.auto": 0.35,      # auto-extracted candidate from free text
    "super-memory.todo": 0.55,      # explicit todo capture
    "super-memory.feedback": 0.6,   # recorded outcome feedback
}
DEFAULT_TRUST_FALLBACK = 0.5


def _default_trust_for_source(source_adapter: str) -> float:
    """Resolve a default trust_score for a source_adapter with no explicit value."""
    return DEFAULT_TRUST_BY_SOURCE.get(source_adapter, DEFAULT_TRUST_FALLBACK)


# ── Factory ──────────────────────────────────────────────────────────────────

def build_envelope(
    content: str,
    *,
    memory_type: str | None = None,
    scope: str | None = None,
    agent_id: str = "lucas",
    session_id: str | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    source_adapter: str = "direct",
    source_id: str | None = None,
    trust_score: float | None = None,
    quality_score: float = 0.5,
    observation_level: str = "explicit",
    provenance_entries: list[dict[str, Any]] | None = None,
    transformations: list[dict[str, Any]] | None = None,
    lifecycle_tier: str = "warm",
    decay_days: int | None = None,
    expires_at: str | None = None,
    auto_pin: bool = False,
    source_ids: list[str] | None = None,
    supersedes_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> MemoryEnvelope:
    """Factory: build a MemoryEnvelope from a plain content string.

    Provides sensible defaults for all P0 fields.
    Use this as the primary entry point for creating envelopes.
    """
    import uuid

    mem_id = str(uuid.uuid4())

    # Resolve enums
    resolved_type = MemoryType(memory_type) if memory_type and memory_type in {e.value for e in MemoryType} else MemoryType.CONTEXT
    resolved_scope = MemoryScope(scope) if scope and scope in {e.value for e in MemoryScope} else MemoryScope.SESSION
    resolved_obs = ObservationLevel(observation_level) if observation_level and observation_level in {e.value for e in ObservationLevel} else ObservationLevel.EXPLICIT

    # Auto quality score if not provided
    if quality_score == 0.5:
        from ..quality_gate import score_quality
        q = score_quality({"content": content, "type": resolved_type.value, "source": source_adapter})
        quality_score = q["quality_score"]

    # Provenance
    prov = ProvenanceChain()
    if provenance_entries:
        for e in provenance_entries:
            prov.add(ProvenanceEntry(**e))
    else:
        prov.add(ProvenanceEntry(
            source_adapter=source_adapter,
            transformation="verbatim",
        ))

    # Lifecycle
    lc = LifecyclePolicy(
        tier=lifecycle_tier,
        decay_days=decay_days,
        expires_at=expires_at,
        auto_pin=auto_pin,
    )

    # Transformations
    tfs = [Transformation(**t) for t in (transformations or [])]

    # Default trust_score by source when caller did not supply one explicitly.
    resolved_trust = trust_score if trust_score is not None else _default_trust_for_source(source_adapter)

    return MemoryEnvelope(
        id=mem_id,
        content=content,
        type=resolved_type,
        scope=resolved_scope,
        agent_id=agent_id,
        session_id=session_id,
        project=project,
        tags=tags or [],
        quality_score=round(quality_score, 4),
        trust_score=resolved_trust,
        confidence_score=resolved_trust,
        provenance=prov,
        source_adapter=source_adapter,
        source_id=source_id,
        transformation_manifest=tfs,
        lifecycle_policy=lc,
        observation_level=resolved_obs,
        source_ids=source_ids or [],
        supersedes_id=supersedes_id,
        metadata=metadata or {},
    )
