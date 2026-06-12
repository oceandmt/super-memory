from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .models import MemoryRecord, SaveResult


@dataclass
class TurnContext:
    agent_id: str
    session_id: str | None = None
    user_message: str | None = None
    assistant_message: str | None = None
    project: str | None = None
    metadata: dict = field(default_factory=dict)


class MemoryLifecycleProvider(Protocol):
    """Hermes-inspired lifecycle hooks for OpenClaw integration."""

    def initialize(self, session_id: str | None = None) -> None: ...

    def prefetch(self, query: str, limit: int = 10) -> list[MemoryRecord]: ...

    def sync_turn(self, context: TurnContext) -> list[SaveResult]: ...

    def on_pre_compress(self, messages: list[dict]) -> list[SaveResult]: ...

    def on_session_end(self, messages: list[dict]) -> list[SaveResult]: ...

    def on_delegation(self, parent: TurnContext, child_summary: str) -> list[SaveResult]: ...
