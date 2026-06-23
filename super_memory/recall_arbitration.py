from __future__ import annotations
import math, re
from datetime import datetime, timezone
from typing import Any

LAYER_WEIGHTS={"workspace_markdown":1.0,"mempalace":0.82,"honcho":0.78,"neural_memory":0.88}
STOP={"the","and","for","with","from","that","this","super","memory"}

def terms(s:str)->set[str]: return {t for t in re.split(r"\W+", s.lower()) if len(t)>2 and t not in STOP}
def recency(created:str|None)->float:
    if not created: return .3
    try:
        dt=datetime.fromisoformat(created.replace('Z','+00:00'))
        days=max(0,(datetime.now(timezone.utc)-dt).days)
        return 1/(1+days/30)
    except Exception: return .3

def score_record(query:str, layer:str, rank:int, rec:dict[str,Any])->dict[str,Any]:
    qt, ct = terms(query), terms(rec.get('content') or '')
    lexical=len(qt & ct)/max(1,len(qt))
    meta=rec.get('metadata') or {}
    trust=float(rec.get('trust_score') or 0.5)
    qual=float(meta.get('quality_score') or (meta.get('quality_gate') or {}).get('quality_score') or 0.5)
    type_boost=.12 if rec.get('type') in {'fact','decision','workflow','insight','lesson','instruction','reference'} else 0
    score=(LAYER_WEIGHTS.get(layer,.6)*.18 + lexical*.28 + recency(rec.get('created_at'))*.10 + trust*.12 + qual*.17 + type_boost + 1/(60+rank+1))
    why=[]
    if lexical: why.append(f"lexical_overlap={lexical:.2f}")
    why.append(f"layer={layer}"); why.append(f"quality={qual:.2f}"); why.append(f"trust={trust:.2f}")
    return {"layer":layer,"rank":rank,"score":round(score,4),"record":rec,"why_selected":why,"citation":rec.get('source') or rec.get('id')}

def arbitrate(query:str, layered:dict[str,list[dict[str,Any]]], limit:int=10)->dict[str,Any]:
    seen=set(); candidates=[]; excluded=[]
    for layer, records in layered.items():
        for i, rec in enumerate(records):
            key=rec.get('id') or (rec.get('content') or '')[:200]
            item=score_record(query, layer, i, rec)
            if key in seen:
                excluded.append({"id":key,"reason":"duplicate_across_layers","layer":layer})
                continue
            seen.add(key); candidates.append(item)
    candidates.sort(key=lambda x:x['score'], reverse=True)
    return {"query":query,"answer_context":candidates[:limit],"selected_memories":[c['record'] for c in candidates[:limit]],"excluded_memories":excluded[:50],"layer_votes":{k:len(v) for k,v in layered.items()},"winner_policy":candidates[0]['layer'] if candidates else 'none',"confidence":candidates[0]['score'] if candidates else 0,"citations":[c['citation'] for c in candidates[:limit] if c.get('citation')],"why":"ranked by layer weight + lexical overlap + recency + trust + quality + type boost"}
