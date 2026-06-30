"""Project inference and backfill utilities."""
from __future__ import annotations
import json
from typing import Any
from .config import load_config
from .models import MemoryRecord, MemoryType, MemoryScope
from .service import infer_project_for_record
from .storage import SuperMemoryStore, row_to_memory
from . import graph


def infer_project_text(content: str, source: str | None = None, tags: list[str] | None = None) -> str | None:
    rec = MemoryRecord(content=content, type=MemoryType.CONTEXT, scope=MemoryScope.SESSION, source=source, tags=tags or [])
    return infer_project_for_record(rec)


def backfill_projects(limit: int = 2000, dry_run: bool = True, config_path: str | None = None, rebuild_graph: bool = False) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    candidates=[]; updated=0; projected=0; projection_errors=[]
    with store.connect() as conn:
        rows=conn.execute("""
            SELECT * FROM memories
            WHERE (project IS NULL OR project='' OR project='(none)')
              AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1
            ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        for row in rows:
            rec=row_to_memory(row)
            project=infer_project_for_record(rec, workspace_root=str(cfg.workspace_root))
            if not project: continue
            candidates.append({"id": rec.id, "layer": row["layer"], "project": project})
            if not dry_run:
                meta=dict(rec.metadata or {})
                meta["project_inferred"] = True
                meta["project_inference_source"] = "backfill_projects"
                conn.execute("UPDATE memories SET project=?, metadata_json=? WHERE id=? AND layer=?", (project, json.dumps(meta, ensure_ascii=False), rec.id, row["layer"]))
                updated += 1
                if rebuild_graph:
                    rec.project = project
                    rec.metadata = meta
                    try:
                        graph.project_memory(rec, config_path=config_path)
                        projected += 1
                    except Exception as exc:
                        projection_errors.append({"id": rec.id, "error": f"{type(exc).__name__}: {exc}"})
        if not dry_run: conn.commit()
    return {"ok": not projection_errors, "dry_run": dry_run, "checked": len(rows), "candidate_count": len(candidates), "updated": updated, "graph_projected": projected, "projection_errors": projection_errors[:20], "candidates": candidates[:50]}
