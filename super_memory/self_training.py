from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .config import load_config

def capture_failed_recall(query:str, wrong_answer:str='', expected_answer:str='', notes:str='', config_path:str|None=None)->dict[str,Any]:
    cfg=load_config(config_path); root=Path(cfg.workspace_root)
    qdir=root/'memory'/'training'; tdir=root/'projects'/'super-memory-github'/'tests'/'recall_cases'
    qdir.mkdir(parents=True, exist_ok=True); tdir.mkdir(parents=True, exist_ok=True)
    ts=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    case={"id":f"failed-recall-{ts}","query":query,"wrong_answer":wrong_answer,"expected_answer":expected_answer,"notes":notes,"created_at":datetime.now(timezone.utc).isoformat(),"expected_contains":[x.strip() for x in expected_answer.split('\n') if x.strip()][:10]}
    with (qdir/'self-training-queue.md').open('a',encoding='utf-8') as f:
        f.write(f"\n## {case['id']}\n- Query: {query}\n- Expected: {expected_answer}\n- Wrong: {wrong_answer}\n- Notes: {notes}\n")
    jpath=tdir/f"{case['id']}.json"; jpath.write_text(json.dumps(case,ensure_ascii=False,indent=2),encoding='utf-8')
    return {"ok":True,"case":case,"queue":str(qdir/'self-training-queue.md'),"test_case":str(jpath)}
