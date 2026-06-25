from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .config import load_config
from .self_heal import self_heal_status, self_heal_embeddings
from .deep_auto import deep_audit, deep_qualify, deep_debug, deep_improve
from .projections.manifest import audit_projection_drift, repair_projection_drift
from .long_memory import review_long_memories
from .recall_benchmark import run_recall_benchmark

def run_scheduled_maintenance(config_path:str|None=None, dry_run:bool=False)->dict:
    cfg=load_config(config_path); ts=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'); out={'ok':True,'timestamp':ts,'dry_run':dry_run,'steps':{}}
    out['steps']['self_heal_before']=self_heal_status(config_path)
    if not dry_run and out['steps']['self_heal_before'].get('missing_vectors',0)>0: out['steps']['self_heal']=self_heal_embeddings(batch_size=100, config_path=config_path)
    out['steps']['projection_drift']=repair_projection_drift(config_path,dry_run=dry_run)
    out['steps']['long_memory_review']=review_long_memories(config_path=config_path)
    out['steps']['deep_audit']=deep_audit(config_path)
    out['steps']['deep_qualify']=deep_qualify(config_path)
    out['steps']['deep_debug']=deep_debug(config_path)
    out['steps']['deep_improve']=deep_improve(dry_run=dry_run,config_path=config_path)
    out['steps']['recall_benchmark']=run_recall_benchmark(config_path)
    out['steps']['self_heal_after']=self_heal_status(config_path)
    rdir=Path(cfg.workspace_root)/'projects'/'super-memory-github'/'reports'/'maintenance'; rdir.mkdir(parents=True,exist_ok=True)
    j=rdir/f'{ts}.json'; m=rdir/f'{ts}.md'; j.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    m.write_text('# Super Memory Maintenance Report\n\n```json\n'+json.dumps(out,ensure_ascii=False,indent=2)+'\n```\n',encoding='utf-8')
    out['report_json']=str(j); out['report_md']=str(m); return out
