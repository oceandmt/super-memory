from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Literal
from .envelope import MemoryEnvelope

Action = Literal['save','skip_duplicate','quarantine','needs_review','promote_existing']

@dataclass
class WriteGateResult:
    allow: bool
    action: Action
    quality_score: float
    reasons: list[str] = field(default_factory=list)
    normalized_type: str = 'context'
    suggested_tags: list[str] = field(default_factory=list)
    conflict_ids: list[str] = field(default_factory=list)
    duplicate_id: str | None = None
    def to_dict(self): return asdict(self)

def evaluate_write(envelope: MemoryEnvelope, *, existing_hashes: dict[str,str] | None=None, conflicts: list[str] | None=None) -> WriteGateResult:
    content=(envelope.content or '').strip(); reasons=[]
    if not content: return WriteGateResult(False,'quarantine',0.0,['empty_content'], envelope.type.value)
    if len(content)<8: reasons.append('too_short')
    if len(content)>4000: reasons.append('long_memory_review')
    if existing_hashes and envelope.content_hash in existing_hashes:
        return WriteGateResult(False,'skip_duplicate',envelope.quality_score,['duplicate_content_hash'], envelope.type.value, duplicate_id=existing_hashes[envelope.content_hash])
    if conflicts:
        return WriteGateResult(True,'needs_review',envelope.quality_score,['possible_conflict'], envelope.type.value, conflict_ids=conflicts)
    allow=envelope.quality_score>=0.25 and content!=''
    action: Action='save' if allow else 'quarantine'
    tags=[]
    if envelope.quality_score>=0.75: tags.append('high-quality')
    if len(content)>2000: tags.append('long-memory')
    return WriteGateResult(allow, action, envelope.quality_score, reasons, envelope.type.value, tags)
