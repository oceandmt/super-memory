from __future__ import annotations

import hashlib, re
from typing import Any
from .semantic_taxonomy import normalize_relations
from .semantic_classifier import classify_semantic_type

TYPE_KEYWORDS = {
    "decision": ["decided", "decision", "chose", "will use", "quyết định"],
    "workflow": ["workflow", "steps", "procedure", "process", "how to", "quy trình"],
    "todo": ["todo", "need to", "cần", "next"],
    "blocker": ["blocked", "blocker", "error", "bug", "failed", "lỗi"],
    "preference": ["prefer", "like", "want", "thích"],
    "fact": ["is located", "path", "version", "installed", "config"],
}
RELATION_PATTERNS = [
    ("CAUSED_BY", r"(.+?)\s+(?:caused by|because of|do)\s+(.+)"),
    ("RESOLVED_BY", r"(.+?)\s+(?:fixed by|resolved by|sửa bằng)\s+(.+)"),
    ("DEPENDS_ON", r"(.+?)\s+(?:depends on|requires|cần)\s+(.+)"),
    ("CONFIGURES", r"(.+?)\s+(?:configures|configured by|cấu hình)\s+(.+)"),
    ("SYNCED_WITH", r"(.+?)\s+(?:synced with|sync with|đồng bộ với)\s+(.+)"),
]
ENTITY_RE = re.compile(r"(?:/[\w.\-]+)+|[A-Z][A-Za-z0-9_.-]{2,}|[\w.-]+/[\w.-]+|v?\d+\.\d+(?:\.\d+)?")

def infer_type(content: str, current: str = "context") -> str:
    """Compatibility view over the calibrated semantic classifier."""
    if current and current != "context":
        return current
    return classify_semantic_type(content).semantic_type

def extract_entities(content: str) -> list[str]:
    seen, out = set(), []
    for m in ENTITY_RE.findall(content):
        if len(m) > 2 and m not in seen:
            seen.add(m); out.append(m)
    return out[:30]

def extract_relations(content: str) -> list[dict[str, str]]:
    rels=[]
    for typ, pat in RELATION_PATTERNS:
        for a,b in re.findall(pat, content, re.I):
            rels.append({"type": typ, "source": a.strip()[:120], "target": b.strip()[:120]})
    return rels[:20]

def score_quality(payload: dict[str, Any]) -> dict[str, Any]:
    content = (payload.get("content") or "").strip()
    score = 0.35
    reasons=[]
    if len(content) >= 20: score += .15
    else: reasons.append("too_short")
    if len(content) > 4000: score -= .15; reasons.append("too_long")
    if payload.get("source"): score += .1
    else: reasons.append("missing_source")
    if payload.get("type") and payload.get("type") != "context": score += .1
    if payload.get("scope") in {"project","shared","cross-agent"}: score += .08
    ents = extract_entities(content)
    rels = normalize_relations(extract_relations(content))
    if ents: score += .1
    if rels: score += .12
    if any(x in content.lower() for x in ["verified", "commit", "test", "proof"]): score += .08
    score = max(0.0, min(1.0, score))
    return {"quality_score": round(score,3), "reasons": reasons, "entities": ents, "relations": rels, "content_hash": hashlib.sha256(content.encode()).hexdigest()}

def apply_quality_gate(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out["content"] = (out.get("content") or "").strip()
    supplied_type = str(out.get("type") or "context")
    classification = classify_semantic_type(out["content"])
    out["type"] = supplied_type if supplied_type != "context" else classification.semantic_type
    meta = dict(out.get("metadata") or {})
    # Orthogonal dimensions: never overload semantic type with truth, storage,
    # visibility or lifecycle semantics.
    meta["semantic_classification"] = classification.as_dict()
    meta.setdefault("truth_level", "asserted")
    meta.setdefault("projection_type", "canonical_memory")
    meta.setdefault("scope", out.get("scope", "session"))
    q = score_quality(out)
    # These fields describe server-observed content.  Never trust a caller's
    # cached/forged copy: stale quality data is worse than no quality data.
    meta["quality_gate"] = q
    meta["quality_score"] = q["quality_score"]
    meta["entities"] = q["entities"]
    meta["relations"] = q["relations"]
    meta["content_hash"] = q["content_hash"]
    meta.setdefault("lifecycle_state", "normalized")
    if out.get("trust_score") is None:
        out["trust_score"] = 0.7 if q["quality_score"] >= .7 else None
    out["metadata"] = meta
    tags = list(out.get("tags") or [])
    for e in q["entities"][:8]:
        tag = f"entity:{e}"[:100]
        if tag not in tags: tags.append(tag)
    if "quality-gated" not in tags: tags.append("quality-gated")
    out["tags"] = tags
    try:
        from .memory_quality import enrich_quality_metadata
        out["metadata"] = enrich_quality_metadata(out["content"], out["type"], out["metadata"], out.get("source"))
        # Keep the legacy gate view and the versioned quality contract on one
        # authoritative score. Otherwise callers can observe two conflicting
        # quality values for the same canonical content.
        authoritative = out["metadata"].get("quality_score")
        if authoritative is not None:
            out["metadata"]["quality_gate"]["quality_score"] = authoritative
    except Exception:
        pass
    return out
