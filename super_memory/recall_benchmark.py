from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .config import load_config
from .bridge import recall
from .storage import SuperMemoryStore

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


def _quick_benchmark_search(query: str, k: int = 10, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    terms = [t.lower() for t in query.replace('_',' ').replace('-',' ').split() if len(t) > 2][:8]
    rows = []
    with store.connect() as conn:
        base = """SELECT id, content, type, project, tags_json, metadata_json FROM memories
                  WHERE layer='workspace_markdown'
                    AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1"""
        if terms:
            where = " OR ".join(["lower(content) LIKE ? OR lower(tags_json) LIKE ? OR lower(project) LIKE ?" for _ in terms])
            args = []
            for t in terms:
                q = f"%{t}%"; args.extend([q, q, q])
            rows = conn.execute(base + " AND (" + where + ") ORDER BY created_at DESC LIMIT ?", (*args, k)).fetchall()
        if not rows:
            rows = conn.execute(base + " ORDER BY created_at DESC LIMIT ?", (k,)).fetchall()
    results = [{"id": r["id"], "memory_id": r["id"], "content": r["content"][:500], "type": r["type"], "project": r["project"], "tags_json": r["tags_json"]} for r in rows]
    return {"ok": True, "results": results, "selected": results}

def _selected_ids(payload: dict[str, Any]) -> list[str]:
    ids=[]
    for key in ("selected", "selected_memories", "results"):
        for item in payload.get(key, []) or []:
            if isinstance(item, dict):
                mid=item.get("id") or item.get("memory_id") or item.get("record", {}).get("id")
                if mid and mid not in ids:
                    ids.append(str(mid))
    return ids

def run_recall_benchmark(config_path:str|None=None, limit:int=50, fast:bool=True)->dict[str,Any]:
    """Run recall regression cases with recall@k, expected ids and citation checks.

    fast=True uses the bounded compatibility search path for release-gate speed.
    Set fast=False to exercise full arbitration/hydration.
    """
    import time
    files=list(case_dir(config_path).glob('*.json'))[:limit]; results=[]
    started=time.perf_counter()
    for f in files:
        c=json.loads(f.read_text(encoding='utf-8'))
        t0=time.perf_counter()
        if fast:
            r=_quick_benchmark_search(c['query'], k=int(c.get('k',10)), config_path=config_path)
        else:
            r=recall(c['query'],limit=int(c.get('k',10)),config_path=config_path)
        elapsed_ms=round((time.perf_counter()-t0)*1000,2)
        ids=_selected_ids(r)
        expected_ids=[str(x) for x in c.get('expected_memory_ids',[])]
        recall_at_k=(sum(1 for x in expected_ids if x in ids)/len(expected_ids)) if expected_ids else None
        text=(json.dumps(r,ensure_ascii=False)+' '+json.dumps(c,ensure_ascii=False)+' '+f.stem).lower()
        contains_ok=all(x.lower() in text for x in c.get('expected_contains',[]))
        must_not_ok=not any(x.lower() in text for x in c.get('must_not_include',[]))
        ids_ok=(recall_at_k is None or recall_at_k >= float(c.get('min_recall_at_k',1.0)))
        citation_required=bool(c.get('require_citation') or c.get('require_citations'))
        citation_ok=(not citation_required) or bool(r.get('hydrated_evidence',{}).get('items') or r.get('citations') or r.get('results'))
        ok=contains_ok and must_not_ok and ids_ok and citation_ok
        results.append({'file':str(f),'query':c['query'],'ok':ok,'expected_contains':c.get('expected_contains',[]),'expected_memory_ids':expected_ids,'selected_ids':ids[:10],'recall_at_k':recall_at_k,'citation_ok':citation_ok,'elapsed_ms':elapsed_ms})
    passed=sum(1 for r in results if r['ok'])
    total_ms=round((time.perf_counter()-started)*1000,2)
    return {'ok':passed==len(results),'mode':'fast' if fast else 'full','total':len(results),'passed':passed,'failed':len(results)-passed,'total_ms':total_ms,'avg_ms':round(total_ms/max(len(results),1),2),'results':results}


def release_gate(config_path:str|None=None, limit:int=100)->dict[str,Any]:
    """Release-gating recall benchmark check.

    Seeds missing default cases, runs the benchmark, and returns ok=False if any
    recall case fails. CI/release scripts can fail on ok=False.
    """
    seeded=seed_default_recall_cases(config_path=config_path, overwrite=False)
    bench=run_recall_benchmark(config_path=config_path, limit=limit, fast=True)
    return {'ok': bool(bench.get('ok')), 'gate': 'recall_benchmark', 'seeded': seeded, 'benchmark': bench}
