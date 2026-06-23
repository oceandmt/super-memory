from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from ..config import load_config
from ..bridge import recall_arbitrate

def run_recall_cases(path: str | None = None, config_path: str | None = None) -> dict[str, Any]:
    cfg=load_config(config_path)
    root=Path(path) if path else Path(cfg.workspace_root)/'projects'/'super-memory-github'/'tests'/'recall_cases'
    cases=[]; passed=0
    for fp in sorted(root.glob('*.json')):
        case=json.loads(fp.read_text(encoding='utf-8'))
        res=recall_arbitrate(case.get('query',''), limit=5, config_path=config_path)
        text=json.dumps(res, ensure_ascii=False).lower()
        expected=case.get('expected_contains') or []
        ok=all(str(x).lower() in text for x in expected)
        passed += int(ok)
        cases.append({'file':str(fp),'ok':ok,'query':case.get('query'),'missing':[x for x in expected if str(x).lower() not in text]})
    return {'ok': passed==len(cases), 'passed': passed, 'total': len(cases), 'cases': cases}
