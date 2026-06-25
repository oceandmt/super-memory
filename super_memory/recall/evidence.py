from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any

@dataclass
class RecallEvidence:
    id: str
    channel: str
    content: str
    score: float = 0.0
    memory_id: str | None = None
    layer: str | None = None
    citation: str | None = None
    why_selected: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self): return asdict(self)

@dataclass
class RecallDecision:
    query: str
    selected: list[RecallEvidence]
    excluded: list[dict[str, Any]] = field(default_factory=list)
    layer_votes: dict[str, int] = field(default_factory=dict)
    confidence: float = 0.0
    def to_dict(self):
        return {'query':self.query,'answer_context':[e.to_dict() for e in self.selected], 'selected_memories':[e.to_dict() for e in self.selected], 'excluded_memories':self.excluded, 'layer_votes':self.layer_votes, 'confidence':self.confidence, 'citations':[e.citation for e in self.selected if e.citation]}
