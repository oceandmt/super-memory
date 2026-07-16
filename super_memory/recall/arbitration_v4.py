from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from .evidence import RecallDecision, RecallEvidence

STOP = {"the", "and", "for", "with", "from", "that", "this", "super", "memory"}
WEIGHTS = {
    "fts": 0.8,
    "vector": 0.85,
    "graph": 0.9,
    "semantic_closet": 0.86,
    "mempalace_drawer": 0.82,
    "honcho_peer": 0.78,
    "session_index": 0.75,
    "recent_context": 0.7,
    "workspace_markdown": 1.0,
    "mempalace": 0.82,
    "honcho": 0.78,
    "neural_memory": 0.88,
}

# A channel prior, quality, and trust describe the candidate, not its relevance
# to this query. Require a small amount of query-derived evidence before those
# priors are allowed to rank it.
MIN_QUERY_EVIDENCE = 0.05


def terms(value: str) -> set[str]:
    value = (value or "").lower()
    words = {term for term in re.split(r"\W+", value) if len(term) > 2 and term not in STOP}
    # CJK has no whitespace and meaningful queries are often 1-3 characters.
    cjk = re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u1100-\u11ff]", value)
    words.update(cjk)
    words.update("".join(cjk[i:i + 2]) for i in range(max(0, len(cjk) - 1)))
    return words


def _freshness(metadata: dict[str, Any]) -> tuple[float, bool]:
    raw = metadata.get("updated_at") or metadata.get("created_at")
    if not raw:
        return 1.0, False
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        age_days = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 86400)
    except (TypeError, ValueError):
        return 1.0, False
    durable = str(metadata.get("type", "")).lower() in {"doctrine", "preference", "identity"}
    stale_after = 3650.0 if durable else 180.0
    return max(0.7, 1.0 - min(age_days / stale_after, 1.0) * 0.3), age_days > stale_after


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _canonical_id(row: dict[str, Any], content: str) -> str:
    """Resolve projection/wrapper rows to one stable canonical identity."""
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    record = row.get("record") if isinstance(row.get("record"), dict) else {}
    for container, fields in (
        (row, ("canonical_id", "memory_id", "source_memory_id")),
        (metadata, ("canonical_id", "memory_id", "source_memory_id")),
        (record, ("canonical_id", "memory_id", "source_memory_id", "id")),
    ):
        for field in fields:
            value = container.get(field)
            if value is not None and str(value).strip():
                return str(value)

    # Projection ids (drawer/fiber/vector wrapper ids) are not canonical. A
    # canonical content hash is therefore a stronger fallback than row.id.
    content_hash = row.get("content_hash") or metadata.get("content_hash")
    if content_hash:
        return f"content:{content_hash}"
    if row.get("id") is not None and str(row["id"]).strip():
        return str(row["id"])
    normalized = " ".join(content.lower().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"content:{digest}"


def _candidate_content(row: dict[str, Any]) -> str:
    record = row.get("record") if isinstance(row.get("record"), dict) else {}
    return str(row.get("content") or row.get("text") or row.get("summary") or record.get("content") or "")


def _score_with_query_evidence(query: str, evidence: RecallEvidence) -> tuple[float, float]:
    query_terms = terms(query)
    content_terms = terms(evidence.content)
    lexical = len(query_terms & content_terms) / max(1, len(query_terms))
    quality = _number(evidence.metadata.get("quality_score"), 0.5)
    trust = _number(evidence.metadata.get("trust_score"), 0.5)
    upstream = _number(evidence.metadata.get("upstream_score"), 0.0)
    freshness, stale = _freshness(evidence.metadata)
    conflict_penalty = 0.12 if evidence.metadata.get("conflicted") and not evidence.metadata.get("verified") else 0.0
    query_evidence = max(lexical, upstream)

    evidence.score = round(
        WEIGHTS.get(evidence.channel, WEIGHTS.get(evidence.layer or "", 0.6)) * 0.18
        + lexical * 0.42
        + quality * 0.20
        + trust * 0.12
        + upstream * 0.08,
        4,
    )
    evidence.score = round(max(0.0, evidence.score * freshness - conflict_penalty), 4)
    evidence.metadata.update({"freshness_score": round(freshness, 4), "stale": stale})
    evidence.why_selected += [
        f"channel={evidence.channel}",
        f"lexical_overlap={lexical:.2f}",
        f"upstream_score={upstream:.2f}",
        f"query_evidence={query_evidence:.2f}",
        f"quality={quality:.2f}",
        f"trust={trust:.2f}",
    ]
    return evidence.score, query_evidence


def score(query: str, evidence: RecallEvidence) -> float:
    """Score one candidate while preserving the original public return type."""
    final_score, _ = _score_with_query_evidence(query, evidence)
    return final_score


def arbitrate_v4(
    query: str,
    channels: dict[str, list[dict[str, Any]]],
    limit: int = 10,
) -> dict[str, Any]:
    candidates: list[RecallEvidence] = []
    excluded: list[dict[str, Any]] = []
    votes: dict[str, int] = {}

    for channel, rows in channels.items():
        votes[channel] = len(rows)
        for row in rows:
            content = _candidate_content(row)
            canonical_id = _canonical_id(row, content)
            metadata = dict(row.get("metadata") or {})
            for key in ("quality_score", "trust_score"):
                if key in row and key not in metadata:
                    metadata[key] = row[key]
            # Keep the channel's query-derived score separate from the final
            # arbitration score so it remains observable and is not overwritten.
            metadata["upstream_score"] = _number(row.get("score", metadata.get("upstream_score")), 0.0)
            evidence = RecallEvidence(
                id=canonical_id,
                channel=channel,
                content=content,
                memory_id=canonical_id,
                layer=row.get("layer"),
                citation=row.get("citation") or row.get("source") or canonical_id,
                metadata=metadata,
            )
            _, query_evidence = _score_with_query_evidence(query, evidence)
            if query_evidence < MIN_QUERY_EVIDENCE:
                excluded.append(
                    {
                        "id": canonical_id,
                        "memory_id": canonical_id,
                        "channel": channel,
                        "reason": "insufficient_query_evidence",
                        "query_evidence": round(query_evidence, 4),
                        "minimum": MIN_QUERY_EVIDENCE,
                    }
                )
                continue
            candidates.append(evidence)

    # Rank before canonical dedup so the strongest channel representation wins,
    # independently of channel dictionary insertion order.
    candidates.sort(key=lambda evidence: (-evidence.score, evidence.memory_id or "", evidence.channel))
    selected: list[RecallEvidence] = []
    seen_canonical: set[str] = set()
    for evidence in candidates:
        canonical_id = evidence.memory_id or evidence.id
        if canonical_id in seen_canonical:
            excluded.append(
                {
                    "id": canonical_id,
                    "memory_id": canonical_id,
                    "channel": evidence.channel,
                    "reason": "duplicate_canonical_memory",
                }
            )
            continue
        seen_canonical.add(canonical_id)
        selected.append(evidence)

    decision = RecallDecision(
        query,
        selected[: max(0, limit)],
        excluded[:100],
        votes,
        selected[0].score if selected and limit > 0 else 0.0,
    )
    output = decision.to_dict()
    output["winner_policy"] = "arbitration_v4" if decision.selected else "none"
    output["citation_objects"] = [
        e.metadata.get("citation_details") for e in decision.selected
        if e.metadata.get("citation_details")
    ]
    output["why"] = (
        "ranked by query evidence + channel weight + lexical overlap + quality + trust; "
        "deduplicated by canonical memory id"
    )
    return output
