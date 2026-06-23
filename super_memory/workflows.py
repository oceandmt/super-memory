from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .config import load_config

def update_project_state(project:str='super-memory-github', summary:str='', facts:dict[str,Any]|None=None, config_path:str|None=None)->dict[str,Any]:
    cfg=load_config(config_path); root=Path(cfg.workspace_root)
    path=root/'memory'/f"develop-{project.replace('_','-').replace('github','memory') if project=='super-memory-github' else project}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    now=datetime.now(timezone.utc).isoformat()
    block=f"\n\n## Update {now}\n\n{summary}\n"
    for k,v in (facts or {}).items(): block += f"- {k}: {v}\n"
    if path.exists():
        with path.open('a',encoding='utf-8') as f: f.write(block)
    else:
        path.write_text(f"# Develop {project}\n"+block,encoding='utf-8')
    return {"ok":True,"path":str(path)}

def issue_memory(title:str, status:str='open', cause:str='', fix:str='', verification:str='', config_path:str|None=None)->dict[str,Any]:
    cfg=load_config(config_path); root=Path(cfg.workspace_root)
    path=root/'memory'/'issues'/(title.lower().replace(' ','-')[:80]+'.md')
    path.parent.mkdir(parents=True, exist_ok=True)
    text=f"# Issue: {title}\n\n- Status: {status}\n- Cause: {cause}\n- Fix: {fix}\n- Verification: {verification}\n- Updated: {datetime.now(timezone.utc).isoformat()}\n"
    path.write_text(text,encoding='utf-8')
    return {"ok":True,"path":str(path)}
