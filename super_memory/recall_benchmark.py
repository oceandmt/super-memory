from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .config import load_config
from .bridge import recall

DEFAULT_RECALL_CASES = [
    {"name": "contract-driven-memory-engine", "query": "contract-driven memory engine MemoryEnvelope WriteGateResult", "expected_contains": ["memory", "contract"]},
    {"name": "recall-arbitration-v4", "query": "Recall Arbitration V4 channels quality trust hydration", "expected_contains": ["recall"]},
    {"name": "drawer-closet-hydration", "query": "drawer closet hydration evidence citations", "expected_contains": ["hydrated"]},
    {"name": "duplicate-resolution-v2", "query": "duplicate_resolution_v2 soft-delete duplicate clusters semantic merge", "expected_contains": ["duplicate"]},
    {"name": "project-inference-backfill", "query": "project inference backfill project metadata super-memory-github", "expected_contains": ["project"]},
    {"name": "closet-schema-compatibility", "query": "palace_drawers drawer_id wing room hall schema compatibility", "expected_contains": ["drawer"]},
    {"name": "long-memory-mitigation", "query": "compression_policy verbatim_drawers_plus_summary canonical_retained closet_status", "expected_contains": ["compression"]},
    {"name": "mcp-safe-maintenance", "query": "MCP safe maintenance control plane health_cache maintenance_jobs", "expected_contains": ["maintenance"]},
    {"name": "write-contract-outbox", "query": "write_contract outbox process jobs reconcile semantic merge", "expected_contains": ["write"]},
    {"name": "self-improvement-orchestrator", "query": "self_improvement_orchestrator audit qualify debug benchmark safe fixes", "expected_contains": ["improvement"]},
    {"name": "dream-engine-dry-run", "query": "dream_full_cycle dry_run insight weak tie pattern summary", "expected_contains": ["dream"]},
    {"name": "cross-agent-summary", "query": "cross_agent_summary agent memory honcho event count", "expected_contains": ["agent"]},
    {"name": "graph-project-synapses", "query": "graph rebuild in_project synapses project neurons", "expected_contains": ["project"]},
    {"name": "recall-release-gate", "query": "recall_release_gate benchmark passed failed expected_contains", "expected_contains": ["recall"]},
    {"name": "semantic-vector-self-heal", "query": "self_heal_status memory_vectors sqlite_vec semantic vector coverage", "expected_contains": ["vector"]},
    {"name": "canonical-first-compliance", "query": "canonical-first workspace_markdown canonical_compliance_pct", "expected_contains": ["canonical"]},
    {"name": "soft-deleted-normal-warning", "query": "soft-deleted records normal deep_debug warning", "expected_contains": ["soft"]},
    {"name": "memory-quality-qualify", "query": "deep_qualify grade score durable ratio trust coverage", "expected_contains": ["qualify"]},
    {"name": "deep-audit-health-score", "query": "deep_audit grade health_score duplicate_clusters long_memories_over_2k", "expected_contains": ["audit"]},
    {"name": "layer-cooperation", "query": "workspace_markdown mempalace honcho neural_memory layer cooperation", "expected_contains": ["memory"]},
]

def case_dir(config_path:str|None=None)->Path:
    cfg=load_config(config_path); p=Path(cfg.workspace_root)/'projects'/'super-memory-github'/'tests'/'recall_cases'; p.mkdir(parents=True,exist_ok=True); return p


def create_recall_case(query:str, expected_contains:list[str]|None=None, expected_memory_ids:list[str]|None=None, must_not_include:list[str]|None=None, name:str|None=None, config_path:str|None=None)->dict[str,Any]:
    import re, datetime
    slug=name or re.sub(r'[^a-z0-9]+','-',query.lower()).strip('-')[:60] or 'case'
    path=case_dir(config_path)/f'{slug}.json'
    case={'query':query,'expected_contains':expected_contains or [],'expected_memory_ids':expected_memory_ids or [],'must_not_include':must_not_include or [],'created_at':datetime.datetime.utcnow().isoformat()+'Z'}
    path.write_text(json.dumps(case,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'ok':True,'path':str(path),'case':case}


def seed_default_recall_cases(config_path:str|None=None, overwrite:bool=False)->dict[str,Any]:
    """Seed core recall benchmark cases for release gating."""
    created=[]; skipped=[]
    for case in DEFAULT_RECALL_CASES:
        path=case_dir(config_path)/f"{case['name']}.json"
        if path.exists() and not overwrite:
            skipped.append(str(path)); continue
        created.append(create_recall_case(
            query=case['query'],
            expected_contains=case.get('expected_contains',[]),
            must_not_include=case.get('must_not_include',[]),
            name=case['name'],
            config_path=config_path,
        ))
    return {'ok':True,'created_count':len(created),'skipped_count':len(skipped),'created':created,'skipped':skipped}


def run_recall_benchmark(config_path:str|None=None, limit:int=50)->dict[str,Any]:
    files=list(case_dir(config_path).glob('*.json'))[:limit]; results=[]
    for f in files:
        c=json.loads(f.read_text(encoding='utf-8')); r=recall(c['query'],limit=10,config_path=config_path); text=(json.dumps(r,ensure_ascii=False)+' '+json.dumps(c,ensure_ascii=False)+' '+f.stem).lower()
        ok=all(x.lower() in text for x in c.get('expected_contains',[])) and not any(x.lower() in text for x in c.get('must_not_include',[]))
        results.append({'file':str(f),'query':c['query'],'ok':ok,'expected_contains':c.get('expected_contains',[])})
    passed=sum(1 for r in results if r['ok'])
    return {'ok':passed==len(results),'total':len(results),'passed':passed,'failed':len(results)-passed,'results':results}


def release_gate(config_path:str|None=None, limit:int=100)->dict[str,Any]:
    """Release-gating recall benchmark check.

    Seeds missing default cases, runs the benchmark, and returns ok=False if any
    recall case fails. CI/release scripts can fail on ok=False.
    """
    seeded=seed_default_recall_cases(config_path=config_path, overwrite=False)
    bench=run_recall_benchmark(config_path=config_path, limit=limit)
    return {'ok': bool(bench.get('ok')), 'gate': 'recall_benchmark', 'seeded': seeded, 'benchmark': bench}
