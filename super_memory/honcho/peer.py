"""Peer modeling — local Honcho-style user/agent representation.

Maintains lightweight peer cards: facts, preferences, habits, goals.
No external Honcho backend required.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class PeerRole(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    PROJECT = "project"
    SYSTEM = "system"


@dataclass
class PeerFact:
    content: str
    type: str = "fact"  # fact, preference, habit, goal, blocker
    confidence: float = 0.7
    source: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PeerModel:
    id: str
    role: PeerRole
    display_name: str | None = None
    facts: list[PeerFact] = field(default_factory=list)
    preferences: list[PeerFact] = field(default_factory=list)
    habits: list[PeerFact] = field(default_factory=list)
    goals: list[PeerFact] = field(default_factory=list)
    blockers: list[PeerFact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_fact(self, fact: PeerFact) -> None:
        """Add fact to correct bucket."""
        bucket = {
            "preference": self.preferences,
            "habit": self.habits,
            "goal": self.goals,
            "blocker": self.blockers,
        }.get(fact.type, self.facts)
        if not any(f.content == fact.content for f in bucket):
            bucket.append(fact)
            self.updated_at = datetime.now().isoformat()

    def to_context_block(self, max_tokens: int = 500) -> str:
        """Generate compact context block for system prompt injection."""
        lines: list[str] = []
        name = self.display_name or self.id
        lines.append(f"Peer: {name} ({self.role.value})")
        
        sections = [
            ("Facts", self.facts[:5]),
            ("Preferences", self.preferences[:5]),
            ("Habits", self.habits[:3]),
            ("Goals", self.goals[:3]),
            ("Blockers", self.blockers[:3]),
        ]
        
        for title, items in sections:
            if items:
                lines.append(f"{title}:")
                for item in items:
                    lines.append(f"- {item.content}")
        
        text = "\n".join(lines)
        words = text.split()
        if len(words) > max_tokens:
            return " ".join(words[:max_tokens]) + " ..."
        return text

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role.value,
            "display_name": self.display_name,
            "facts": [f.__dict__ for f in self.facts],
            "preferences": [f.__dict__ for f in self.preferences],
            "habits": [f.__dict__ for f in self.habits],
            "goals": [f.__dict__ for f in self.goals],
            "blockers": [f.__dict__ for f in self.blockers],
            "metadata": self.metadata,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PeerModel":
        model = cls(
            id=data["id"],
            role=PeerRole(data["role"]),
            display_name=data.get("display_name"),
            metadata=data.get("metadata", {}),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )
        for key in ["facts", "preferences", "habits", "goals", "blockers"]:
            setattr(model, key, [PeerFact(**f) for f in data.get(key, [])])
        return model


class PeerStore:
    """SQLite persistence for peer models."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS honcho_peers (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    display_name TEXT,
                    model_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_honcho_peers_role ON honcho_peers(role)")

    def get(self, peer_id: str) -> PeerModel | None:
        with self._connect() as conn:
            row = conn.execute("SELECT model_json FROM honcho_peers WHERE id = ?", (peer_id,)).fetchone()
        if not row:
            return None
        return PeerModel.from_dict(json.loads(row["model_json"]))

    def save(self, model: PeerModel) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO honcho_peers
                (id, role, display_name, model_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    model.id,
                    model.role.value,
                    model.display_name,
                    json.dumps(model.to_dict(), ensure_ascii=False),
                    model.updated_at,
                ),
            )

    def list_peers(self, role: PeerRole | None = None) -> list[PeerModel]:
        with self._connect() as conn:
            if role:
                rows = conn.execute("SELECT model_json FROM honcho_peers WHERE role = ?", (role.value,)).fetchall()
            else:
                rows = conn.execute("SELECT model_json FROM honcho_peers ORDER BY updated_at DESC").fetchall()
        return [PeerModel.from_dict(json.loads(r["model_json"])) for r in rows]

    def get_or_create(self, peer_id: str, role: PeerRole = PeerRole.HUMAN, display_name: str | None = None) -> PeerModel:
        model = self.get(peer_id)
        if model:
            return model
        model = PeerModel(id=peer_id, role=role, display_name=display_name)
        self.save(model)
        return model
