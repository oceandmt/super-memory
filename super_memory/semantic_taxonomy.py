from __future__ import annotations

RELATION_TYPES = {
    "CAUSED_BY", "LEADS_TO", "RESOLVED_BY", "CONTRADICTS", "SUPERSEDES",
    "DEPENDS_ON", "IMPLEMENTS", "CONFIGURES", "INSTALLED_AT", "SYNCED_WITH",
    "EVIDENCE_FOR", "EVIDENCE_AGAINST", "DERIVED_FROM", "MENTIONS",
}

def canonical_entity(name: str, aliases: dict[str, str] | None = None) -> str:
    key = " ".join((name or "").strip().lower().replace("_", "-").split())
    defaults = {"super-memory": "super-memory", "super memory": "super-memory", "super_memory": "super-memory", "projects/super-memory-github": "super-memory-github", "oceandmt/super-memory": "super-memory-github"}
    merged = {**defaults, **(aliases or {})}
    return merged.get(key, key)

def normalize_relations(relations):
    out=[]
    for r in relations or []:
        typ=str(r.get("type", "MENTIONS")).upper()
        if typ not in RELATION_TYPES: typ="MENTIONS"
        out.append({"type":typ,"source":canonical_entity(str(r.get("source",""))),"target":canonical_entity(str(r.get("target","")))})
    return out
