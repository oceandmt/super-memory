from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


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
    vector_enabled: bool = False  # Enable vector embedding recall (requires sqlite-vec)
    legacy_graph_edges: bool = True  # dual-write to graph_edges for backward compat; set False to disable
