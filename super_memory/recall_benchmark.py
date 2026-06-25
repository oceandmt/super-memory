from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .config import load_config
from .bridge import recall

def case_dir(config_path:str|None=None)->Path:
    cfg=load_config(config_path); p=Path(cfg.workspace_root)/'projects'/'super-memory-github'/'tests'/'recall_cases'; p.mkdir(parents=True,exist_ok=True); return p

def create_recall_case(query:str, expected_contains:list[str]|None=None, expected_memory_ids:list[str]|None=None, must_not_include:list[str]|None=None, name:str|None=None, config_path:str|None=None)->dict[str,Any]:
    import re, datetime
    slug=name or re.sub(r'[^a-z0-9]+','-',query.lower()).strip('-')[:60] or 'case'
    path=case_dir(config_path)/f'{slug}.json'
    case={'query':query,'expected_contains':expected_contains or [],'expected_memory_ids':expected_memory_ids or [],'must_not_include':must_not_include or [],'created_at':datetime.datetime.utcnow().isoformat()+'Z'}
    path.write_text(json.dumps(case,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'ok':True,'path':str(path),'case':case}

def run_recall_benchmark(config_path:str|None=None, limit:int=50)->dict[str,Any]:
    files=list(case_dir(config_path).glob('*.json'))[:limit]; results=[]
    for f in files:
        c=json.loads(f.read_text(encoding='utf-8')); r=recall(c['query'],limit=10,config_path=config_path); text=json.dumps(r,ensure_ascii=False).lower()
        ok=all(x.lower() in text for x in c.get('expected_contains',[])) and not any(x.lower() in text for x in c.get('must_not_include',[]))
        results.append({'file':str(f),'query':c['query'],'ok':ok,'expected_contains':c.get('expected_contains',[])})
    passed=sum(1 for r in results if r['ok'])
    return {'ok':passed==len(results),'total':len(results),'passed':passed,'failed':len(results)-passed,'results':results}
