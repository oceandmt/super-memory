"""Dreaming narrative — generate markdown narrative from cross-domain patterns.

Matches OpenClaw memory-core dreaming-narrative.ts:
- Creates narrative markdown files from dream patterns
- Builds human-readable summaries of cognitive bridges
- Links to source memories via citations
"""

from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .models import MemoryLayer, MemoryRecord
from .storage import SuperMemoryStore

logger = logging.getLogger(__name__)


def generate_narrative(
    *,
    title: str = "Dreaming Narrative",
    out_dir: str | None = None,
    max_insights: int = 10,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Generate a narrative markdown document from cognitive insights.

    Scans neural_memory layer for insight-type memories created by
    the dream engine and compiles them into a narrative markdown file.

    Args:
        title: Narrative document title
        out_dir: Output directory (default: workspace/memory/)
        max_insights: Max insights to include
        config_path: Super Memory config path

    Returns:
        Dict with path, sections count, insights included
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    root = Path(cfg.workspace_root)
    out_path = Path(out_dir) if out_dir else root / "memory"
    out_path.mkdir(parents=True, exist_ok=True)

    # Query insight/fact memories from neural_memory
    insights: list[MemoryRecord] = []
    try:
        with store.connect() as conn:
            # Check if metadata column exists
            cols = [c[1] for c in conn.execute('PRAGMA table_info(memories)').fetchall()]
            select_cols = "m.id, m.content"
            if 'metadata' in cols:
                select_cols += ", m.metadata"
            if 'created_at' in cols:
                select_cols += ", m.created_at"
            rows = conn.execute(
                f"""SELECT {select_cols}
                   FROM memories m
                   WHERE m.layer = ? AND m.type IN ('insight', 'fact', 'decision')
                   ORDER BY m.id DESC
                   LIMIT ?""",
                (MemoryLayer.NEURAL_MEMORY.value, max_insights * 3),
            ).fetchall()

        for row in rows:
            insights.append(MemoryRecord(
                id=str(row[0]),
                content=str(row[1]) or "",
                layer=MemoryLayer.NEURAL_MEMORY,
                type="insight",
            ))
    except Exception as exc:
        return {"ok": True, "path": "", "sections": 0, "note": f"query failed: {exc}"}

    if not insights:
        return {"ok": True, "path": "", "sections": 0, "note": "no insights found"}

    # Build narrative sections
    sections: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    for idx, insight in enumerate(insights[:max_insights], 1):
        section = (
            f"### {idx}. Cognitive Bridge\n\n"
            f"{insight.content}\n\n"
        )
        sources = _find_sources(store, insight.id)
        if sources:
            section += f"*Sources: {', '.join(sources[:3])}*\n\n"
        sections.append(section)

    # Write narrative file
    narrative_path = out_path / f"narrative-{datetime.now(timezone.utc).strftime('%Y%m%d')}.md"
    content = (
        f"# {title}\n\n"
        f"*Generated: {now}*\n\n"
        f"---\n\n"
        + "\n---\n\n".join(sections)
    )

    narrative_path.write_text(content, encoding="utf-8")
    logger.info(f"narrative: wrote {len(sections)} sections to {narrative_path}")

    return {
        "ok": True,
        "path": str(narrative_path),
        "sections": len(sections),
        "insights_used": min(len(insights), max_insights),
        "total_available": len(insights),
    }


def _find_sources(store: SuperMemoryStore, memory_id: str) -> list[str]:
    """Find source memory paths for a given memory."""
    try:
        with store.connect() as conn:
            # Try using graph_edges first
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            if 'cognitive_synapses' in tables:
                rows = conn.execute(
                    """SELECT DISTINCT m.source FROM memories m
                       JOIN cognitive_synapses s ON s.target_id = m.id
                       WHERE s.source_id = ? AND m.source IS NOT NULL AND m.source != ''
                       LIMIT 5""",
                    (memory_id,),
                ).fetchall()
                return [r[0] for r in rows if r[0]]
            elif 'graph_edges' in tables:
                rows = conn.execute(
                    """SELECT DISTINCT m.source FROM memories m
                       JOIN graph_edges e ON e.target_id = m.id
                       WHERE e.source_id = ? AND m.source IS NOT NULL AND m.source != ''
                       LIMIT 5""",
                    (memory_id,),
                ).fetchall()
                return [r[0] for r in rows if r[0]]
    except Exception:
        pass
    return []
