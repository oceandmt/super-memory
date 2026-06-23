"""REM extraction pipeline — Rapid Evidence-based Memories from session transcripts.

Matches OpenClaw memory-core rem-evidence.ts + short-term-promotion.ts:
- Extracts grounded evidence chunks from session transcripts
- Scores evidence by confidence (verbatim match > summary > inference)
- Promotes high-confidence evidence to durable memory
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .models import MemoryLayer, MemoryRecord, MemoryScope, MemoryType
from .service import SuperMemoryService
from .storage import SuperMemoryStore

logger = logging.getLogger(__name__)


@dataclass
class EvidenceChunk:
    """One piece of grounded evidence extracted from a transcript."""

    content: str
    confidence: float  # 0.0-1.0
    source_path: str
    source_session: str
    evidence_type: str  # "verbatim", "summary", "inference"
    timestamp: str = ""


class REMExtractor:
    """REM extraction from session transcripts."""

    def __init__(self, config_path: str | None = None):
        self.cfg = load_config(config_path)
        self.store = SuperMemoryStore(self.cfg)
        self.svc = SuperMemoryService(self.cfg)

    def extract_from_session(
        self,
        file_path: str,
        *,
        min_confidence: float = 0.6,
    ) -> list[EvidenceChunk]:
        """Extract evidence chunks from a single session transcript."""
        evidence: list[EvidenceChunk] = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except (OSError, IOError) as exc:
            logger.warning(f"rem: cannot read {file_path}: {exc}")
            return evidence

        lines = text.splitlines()
        session_id = self._extract_session_id(file_path)

        # Extract verbatim user/assistant exchanges (highest confidence)
        current_role = ""
        current_block: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("user:"):
                if current_block:
                    chunk = self._make_chunk(
                        "\n".join(current_block), "verbatim", 0.95, file_path, session_id
                    )
                    if chunk.confidence >= min_confidence:
                        evidence.append(chunk)
                current_role = "user"
                current_block = [stripped[5:].strip()]
            elif stripped.startswith("assistant:") or stripped.startswith("assistant "):
                if current_block:
                    chunk = self._make_chunk(
                        "\n".join(current_block), "verbatim", 0.95, file_path, session_id
                    )
                    if chunk.confidence >= min_confidence:
                        evidence.append(chunk)
                current_role = "assistant"
                current_block = [stripped.split(":", 1)[-1].strip()]
            elif current_role and stripped:
                current_block.append(stripped)

        # Final block
        if current_block:
            chunk = self._make_chunk(
                "\n".join(current_block), "verbatim", 0.90, file_path, session_id
            )
            if chunk.confidence >= min_confidence:
                evidence.append(chunk)

        return evidence

    def _make_chunk(
        self, content: str, etype: str, base_conf: float, path: str, session_id: str
    ) -> EvidenceChunk:
        # Penalize very short or very long chunks
        length = len(content)
        if length < 20:
            base_conf *= 0.5
        elif length > 2000:
            base_conf *= 0.8

        return EvidenceChunk(
            content=content[:2000],
            confidence=min(1.0, base_conf),
            source_path=path,
            source_session=session_id,
            evidence_type=etype,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def promote_evidence(
        self,
        evidence: list[EvidenceChunk],
        *,
        min_confidence: float = 0.7,
        max_per_session: int = 10,
    ) -> list[dict[str, Any]]:
        """Promote high-confidence evidence to durable memory."""
        promoted: list[dict[str, Any]] = []
        high_conf = [e for e in evidence if e.confidence >= min_confidence][:max_per_session]

        for chunk in high_conf:
            try:
                record = MemoryRecord(
                    content=chunk.content,
                    type=MemoryType.FACT,
                    scope=MemoryScope.PROJECT,
                    agent_id="rem",
                    source=f"rem:{chunk.source_session}",
                    tags=["rem", "evidence", chunk.evidence_type],
                    metadata={
                        "confidence": chunk.confidence,
                        "evidence_type": chunk.evidence_type,
                        "source_path": chunk.source_path,
                        "source_session": chunk.source_session,
                    },
                )
                results = self.svc.save(record)
                promoted.append({
                    "content_preview": chunk.content[:100],
                    "confidence": chunk.confidence,
                    "type": chunk.evidence_type,
                    "save_results": [r.model_dump() for r in results],
                })
            except Exception as exc:
                logger.error(f"rem: promote failed: {exc}")

        return promoted

    def _extract_session_id(self, path: str) -> str:
        m = re.search(r"sessions?/([^/]+?)(?:/|$|\.)", path.replace("\\", "/"))
        return m.group(1) if m else "unknown"


def rem_extract_all(
    *,
    min_confidence: float = 0.6,
    promote: bool = True,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Extract REM evidence from all session transcripts and optionally promote."""
    cfg = load_config(config_path)
    extractor = REMExtractor(config_path=config_path)

    sessions_dir = Path(cfg.workspace_root) / "sessions"
    if not sessions_dir.is_dir():
        return {"ok": False, "error": f"sessions dir not found: {sessions_dir}", "extracted": 0}

    all_evidence: list[EvidenceChunk] = []
    files_scanned = 0

    for fpath in sessions_dir.rglob("*.md"):
        evidence = extractor.extract_from_session(str(fpath), min_confidence=min_confidence)
        all_evidence.extend(evidence)
        files_scanned += 1

    promoted = []
    if promote and all_evidence:
        promoted = extractor.promote_evidence(all_evidence, min_confidence=0.7)

    return {
        "ok": True,
        "files_scanned": files_scanned,
        "evidence_extracted": len(all_evidence),
        "promoted": len(promoted),
        "promoted_details": promoted,
    }
