"""Super Memory data models: MemoryRecord, MemoryType, MemoryScope, SaveResult.

Core domain types used across all layers:
- MemoryType: FACT, DECISION, PREFERENCE, TODO, BLOCKER, WORKFLOW, INSIGHT, CONTEXT, DOCTRINE, LESSON, EVENT, BOUNDARY
- MemoryScope: SESSION, AGENT_LOCAL, SHARED, PROJECT, CROSS_AGENT
- MemoryLayer: WORKSPACE_MARKDOWN, MEMPALACE, HONCHO, NEURAL_MEMORY
- MemoryRecord: canonical memory payload with metadata (content_hash, arousal, valence, etc.)
- SaveResult: per-layer save outcome with pending_canonical_sync flag
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

# ── Canonical soft-delete SQL guard ─────────────────────────────────────────
# Single source of truth for "alive" (not soft-deleted) memory rows. Historically
# this predicate was hand-written in bridge/cleanup/conflict/version/service and
# omitted entirely in dream_engine (E7) and hybrid_recall (E8), each omission a
# real recall/stat leak. Import this instead of re-typing the JSON path.
#
#   ALIVE_SQL          -> bare predicate, no table alias  ("...soft_deleted...!=1")
#   alive_sql("m")     -> same predicate with a table alias prefix
ALIVE_SQL = "COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1"


def alive_sql(alias: str | None = None) -> str:
    """Return the soft-delete guard, optionally prefixed with a table alias.

    alive_sql()      -> "COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)!=1"
    alive_sql("m")   -> "COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0)!=1"
    """
    if not alias:
        return ALIVE_SQL
    return f"COALESCE(json_extract({alias}.metadata_json,'$.soft_deleted'),0)!=1"


class MemoryType(str, Enum):
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


class MemoryScope(str, Enum):
    SESSION = "session"
    AGENT_LOCAL = "agent-local"
    SHARED = "shared"
    PROJECT = "project"
    CROSS_AGENT = "cross-agent"


class MemoryLayer(str, Enum):
    WORKSPACE_MARKDOWN = "workspace_markdown"
    MEMPALACE = "mempalace"
    HONCHO = "honcho"
    NEURAL_MEMORY = "neural_memory"


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    content: str
    type: MemoryType = MemoryType.CONTEXT
    scope: MemoryScope = MemoryScope.SESSION
    agent_id: str = "lucas"
    session_id: str | None = None
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    trust_score: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def normalized_tags(self) -> list[str]:
        base = [
            f"agent:{self.agent_id}",
            f"scope:{self.scope.value}",
            f"type:{self.type.value}",
        ]
        if self.project:
            base.append(f"project:{self.project}")
        seen: set[str] = set()
        out: list[str] = []
        for tag in [*base, *self.tags]:
            if tag and tag not in seen:
                seen.add(tag)
                out.append(tag)
        return out


class SaveResult(BaseModel):
    layer: MemoryLayer
    ok: bool
    reference: str | None = None
    message: str | None = None
    pending_canonical_sync: bool = False


# ── Sub-config groups for rationalized configuration ──────────────────────

class RecallConfig(BaseModel):
    """Recall and retrieval configuration."""
    spreading_activation_depth: int = 2
    spreading_activation_top_k: int = 20
    spreading_activation_seed_limit: int = 30
    graph_expansion_enabled: bool = True
    graph_expansion_max_neighbors: int = 10
    graph_expansion_min_weight: float = 0.3
    goal_directed_recall_enabled: bool = True
    rrf_k: float = 60.0
    recall_max_tokens: int = 2000

class VectorConfig(BaseModel):
    """Vector embedding configuration."""
    enabled: bool = False
    provider: str = "ollama"
    model: str = "nomic-embed-text"
    endpoint: str = "http://127.0.0.1:11434/api/embed"
    dimension: int = 768
    batch_size: int = 8
    retry_on_failure: bool = True

class ConsolidationConfig(BaseModel):
    """Consolidation and lifecycle configuration."""
    prune_weight_threshold: float = 0.05
    prune_min_inactive_days: float = 7.0
    dedup_threshold: float = 0.85
    semantic_discovery_enabled: bool = True
    semantic_discovery_min_weight: float = 0.25
    stage_promotion_enabled: bool = True
    mature_enabled: bool = True
    enrich_enabled: bool = True
    dreaming_enabled: bool = True
    short_term_repair_enabled: bool = True

class SimHashConfig(BaseModel):
    """SimHash near-dup detection."""
    enabled: bool = True
    threshold: int = 3
    index_limit: int = 500


class SuperMemoryConfig(BaseModel):
    # Fresh installs must not silently attach to a live OpenClaw workspace.
    # Operators can still opt in explicitly with SUPER_MEMORY_WORKSPACE_ROOT
    # or a concrete config file.
    workspace_root: Path = Field(default_factory=Path.cwd)
    daily_memory_dir: str = "memory"
    long_term_file: str = "MEMORY.md"
    registers_dir: str = "memory/registers"
    sqlite_path: str = "data/super-memory.sqlite3"
    enabled_layers: list[MemoryLayer] = Field(
        default_factory=lambda: [
            MemoryLayer.WORKSPACE_MARKDOWN,
            MemoryLayer.MEMPALACE,
            MemoryLayer.HONCHO,
            MemoryLayer.NEURAL_MEMORY,
        ]
    )
    require_canonical_first: bool = True
    neural_memory_embed_llm_mode: str = "optional"  # optional|disabled|external
    api_token: str = ""  # Bearer token for REST API auth; empty = no auth (backward compat)
    db_backend: str = "sqlite"  # Database backend: "sqlite" (default) or "postgres" (experimental)
    legacy_graph_edges: bool = True  # dual-write to graph_edges for backward compat; set False to disable

    # Backward-compat aliases (mapped from flat config)
    vector_enabled: bool = False  # Maps to vector.enabled
    embedding_provider: str = "ollama"  # Maps to vector.provider
    embedding_model: str = "nomic-embed-text"  # Maps to vector.model
    embedding_endpoint: str = "http://127.0.0.1:11434/api/embed"  # Maps to vector.endpoint
    embedding_dimension: int = 768  # Maps to vector.dimension

    # Sub-config groups
    recall: RecallConfig = Field(default_factory=RecallConfig)
    vector: VectorConfig = Field(default_factory=VectorConfig)
    consolidation: ConsolidationConfig = Field(default_factory=ConsolidationConfig)
    simhash: SimHashConfig = Field(default_factory=SimHashConfig)
