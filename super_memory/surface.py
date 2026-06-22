"""Knowledge Surface — compact graph snapshot for prompt context (~1000 tokens).

Ported from neural-memory v4.58.0 surface/generator.py.
Generates a readable, compact representation of the current memory graph
for efficient prompt injection: top entities, recent decisions, active
workflows, and graph statistics.

The surface is regenerated periodically (not on every recall) and stored
as a cached snapshot.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("super-memory.surface")

DEFAULT_MAX_TOKENS = 1000
SURFACE_CACHE_KEY = "_surface_cache_v1"


def generate(
    config_path: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_entities: int = 15,
    max_decisions: int = 8,
    max_workflows: int = 5,
) -> dict[str, Any]:
    """Generate a Knowledge Surface snapshot from the memory graph.

    Returns a compact dict with:
    - info: memory counts, layers, graph stats
    - top_entities: most frequent entity types
    - recent_decisions: last N decision/instruction memories
    - active_workflows: recent workflow memories
    - top_tags: most common tags
    - summary: ~200 char plain-text summary
    """
    from .config import load_config
    from .storage import SuperMemoryStore

    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)

    # Cache check: prevent regeneration within 60 seconds
    try:
        cache_path = Path(cfg.workspace_root) / "data" / SURFACE_CACHE_KEY
        if cache_path.exists():
            import time
            age = time.time() - cache_path.stat().st_mtime
            if age < 60:
                with open(cache_path) as f:
                    return json.load(f)
    except Exception:
        pass

    result = _generate_surface(store, cfg, max_entities, max_decisions, max_workflows, max_tokens)

    # Write cache
    try:
        cache_path = Path(cfg.workspace_root) / "data" / SURFACE_CACHE_KEY
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(result, f, ensure_ascii=False, default=str)
    except Exception:
        pass

    return result


def _generate_surface(
    store: SuperMemoryStore,
    cfg: Any,
    max_entities: int,
    max_decisions: int,
    max_workflows: int,
    max_tokens: int,
) -> dict[str, Any]:
    """Generate surface without cache layer."""
    with store.connect() as conn:
        # Basic info
        total = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        type_dist = {
            r["type"]: r["c"]
            for r in conn.execute(
                "SELECT type, COUNT(*) as c FROM memories WHERE type IS NOT NULL GROUP BY type"
            ).fetchall()
        }

        # Graph stats
        neurons = conn.execute("SELECT COUNT(*) as c FROM cognitive_neurons").fetchone()["c"]
        synapses = conn.execute("SELECT COUNT(*) as c FROM cognitive_synapses").fetchone()["c"]
        fibers = conn.execute("SELECT COUNT(*) as c FROM cognitive_fibers").fetchone()["c"]

        # Top tags
        tag_rows = conn.execute(
            "SELECT tags_json FROM memories WHERE tags_json IS NOT NULL AND tags_json != '[]' "
            "ORDER BY rowid DESC LIMIT 500"
        ).fetchall()
        tag_counter: Counter = Counter()
        for row in tag_rows:
            try:
                tags = json.loads(row["tags_json"])
                if isinstance(tags, list):
                    for t in tags:
                        if isinstance(t, str) and len(t) > 1:
                            tag_counter[t] += 1
            except Exception:
                pass
        top_tags = [{"tag": t, "count": c} for t, c in tag_counter.most_common(10)]

        # Recent decisions (highest priority type = decision, instruction, workflow)
        recent_decisions_raw = conn.execute(
            "SELECT id, content, type, created_at FROM memories "
            "WHERE type IN ('decision', 'instruction', 'insight', 'preference') "
            "AND (json_extract(metadata_json, '$.soft_deleted') IS NULL "
            "OR json_extract(metadata_json, '$.soft_deleted') != 1) "
            "ORDER BY rowid DESC LIMIT ?",
            (max_decisions,),
        ).fetchall()

        recent_decisions = []
        for r in recent_decisions_raw:
            content_raw = r["content"] or ""
            content = content_raw[:100] + ("..." if len(content_raw) > 100 else "")
            recent_decisions.append({
                "type": r["type"],
                "content": content,
                "id": r["id"][:12],
            })

        # Active workflows
        workflows_raw = conn.execute(
            "SELECT id, content, created_at FROM memories "
            "WHERE type = 'workflow' "
            "AND (json_extract(metadata_json, '$.soft_deleted') IS NULL "
            "OR json_extract(metadata_json, '$.soft_deleted') != 1) "
            "ORDER BY rowid DESC LIMIT ?",
            (max_workflows,),
        ).fetchall()

        workflows = []
        for r in workflows_raw:
            content_raw = r["content"] or ""
            content = content_raw[:120] + ("..." if len(content_raw) > 120 else "")
            workflows.append({
                "content": content,
                "id": r["id"][:12],
            })

        # Recent entity types from extracted_entities
        entity_types: Counter = Counter()
        entity_rows = conn.execute(
            "SELECT metadata_json FROM memories "
            "WHERE json_extract(metadata_json, '$.extracted_entities') IS NOT NULL "
            "ORDER BY rowid DESC LIMIT 300"
        ).fetchall()
        for row in entity_rows:
            try:
                meta = json.loads(row["metadata_json"])
                entities = meta.get("extracted_entities", {})
                if isinstance(entities, dict):
                    for etype in entities.get("entity_types", []):
                        entity_types[etype] += 1
            except Exception:
                pass
        top_entities = [{"type": t, "count": c} for t, c in entity_types.most_common(max_entities)]

    # Build summary (~200 chars)
    type_summary = ", ".join(f"{k}:{v}" for k, v in sorted(type_dist.items(), key=lambda x: -x[1])[:6] if v > 0)
    summary = (
        f"Memory: {total} items ({type_summary}). "
        f"Graph: {neurons} neurons, {synapses} synapses, {fibers} fibers."
    )

    return {
        "ok": True,
        "info": {
            "total_memories": total,
            "type_distribution": type_dist,
            "graph_neurons": neurons,
            "graph_synapses": synapses,
            "graph_fibers": fibers,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "summary": summary,
        "top_tags": top_tags,
        "top_entities": top_entities,
        "recent_decisions": recent_decisions,
        "active_workflows": workflows,
    }


def to_prompt_block(surface: dict[str, Any] | None = None, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """Format Knowledge Surface as a compact prompt block.

    If surface is None, generates a fresh one.
    Trims to fit within max_tokens using token budget.
    """
    if surface is None:
        surface = generate(max_tokens=max_tokens)

    if not surface.get("ok"):
        return "[Knowledge Surface unavailable]"

    # Apply token budget trimming
    surface = _trim_surface_to_budget(surface, max_tokens)

    lines: list[str] = ["[Knowledge Surface]", ""]

    # Summary
    lines.append(f"// {surface.get('summary', '')}")
    lines.append("")

    # Top tags
    tags = surface.get("top_tags", [])
    if tags:
        tags_str = ", ".join(f"{t['tag']}({t['count']})" for t in tags[:5])
        lines.append(f"Top tags: {tags_str}")

    # Top entities
    entities = surface.get("top_entities", [])
    if entities:
        entities_str = ", ".join(f"{e['type']}({e['count']})" for e in entities[:5])
        lines.append(f"Entities: {entities_str}")

    # Recent decisions
    decisions = surface.get("recent_decisions", [])
    if decisions:
        lines.append("")
        lines.append("Recent:")
        for d in decisions:
            lines.append(f"  [{d['type']}] {d['content']}")

    # Active workflows
    workflows = surface.get("active_workflows", [])
    if workflows:
        lines.append("")
        lines.append("Workflows:")
        for w in workflows:
            lines.append(f"  {w['content']}")

    # Clusters (new: auto-inferred group names)
    clusters = surface.get("clusters", [])
    if clusters:
        lines.append("")
        lines.append("Clusters:")
        for c in clusters[:3]:
            lines.append(f"  - {c}")

    return "\n".join(lines)


def _trim_surface_to_budget(surface: dict, budget: int) -> dict:
    """Trim surface to fit within token budget (priority-based)."""
    current_tokens = len(str(surface)) // 3
    if current_tokens <= budget:
        return surface
    result = dict(surface)
    # Truncate lists
    if "top_tags" in result and len(result["top_tags"]) > 5:
        result["top_tags"] = result["top_tags"][:5]
    if "top_entities" in result and len(result["top_entities"]) > 3:
        result["top_entities"] = result["top_entities"][:3]
    if "recent_decisions" in result and len(result["recent_decisions"]) > 3:
        result["recent_decisions"] = result["recent_decisions"][:3]
    if "active_workflows" in result and len(result["active_workflows"]) > 2:
        result["active_workflows"] = result["active_workflows"][:2]
    # Truncate content fields
    for key in ["recent_decisions", "active_workflows"]:
        if key in result:
            for item in result[key]:
                if "content" in item and len(item["content"]) > 60:
                    item["content"] = item["content"][:60] + "..."
    return result


def invalidate_cache(config_path: str | None = None) -> bool:
    """Force cache invalidation so next generate() rebuilds."""
    from .config import load_config

    cfg = load_config(config_path)
    cache_path = Path(cfg.workspace_root) / "data" / SURFACE_CACHE_KEY
    if cache_path.exists():
        cache_path.unlink()
        return True
    return False
