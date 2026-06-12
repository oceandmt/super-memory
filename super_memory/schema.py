from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class PalaceHall(str, Enum):
    FACTS = "facts"
    EVENTS = "events"
    DISCOVERIES = "discoveries"
    PREFERENCES = "preferences"
    ADVICE = "advice"
    WORKFLOWS = "workflows"
    BLOCKERS = "blockers"
    LESSONS = "lessons"


class PalaceDrawer(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    wing: str
    room: str
    hall: PalaceHall
    content: str
    source: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PeerRole(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    PROJECT = "project"
    SYSTEM = "system"


class Peer(BaseModel):
    id: str
    role: PeerRole
    display_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace: str = "openclaw"
    session_id: str | None = None
    observer_peer_id: str
    observed_peer_id: str | None = None
    content: str
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GraphRelation(str, Enum):
    RELATED_TO = "related_to"
    CAUSED_BY = "caused_by"
    LEADS_TO = "leads_to"
    RESOLVED_BY = "resolved_by"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    MENTIONS_ENTITY = "mentions_entity"


class GraphEdge(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_memory_id: str
    target_memory_id: str
    relation: GraphRelation = GraphRelation.RELATED_TO
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryTier(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class LifecycleState(str, Enum):
    ACTIVE = "active"
    PINNED = "pinned"
    SUPERSEDED = "superseded"
    SOFT_DELETED = "soft_deleted"
    EXPIRED = "expired"
