from __future__ import annotations
import re
from typing import Any
from .evidence import RecallEvidence, RecallDecision
STOP={'the','and','for','with','from','that','this','super','memory'}
WEIGHTS={'fts':.8,'vector':.85,'graph':.9,'semantic_closet':.86,'mempalace_drawer':.82,'honcho_peer':.78,'session_index':.75,'recent_context':.7,'workspace_markdown':1.0,'mempalace':.82,'honcho':.78,'neural_memory':.88}
def terms(s): return {t for t in re.split(r'\W+', (s or '').lower()) if len(t)>2 and t not in STOP}
def score(query, ev:RecallEvidence):
    qt=terms(query); ct=terms(ev.content); lex=len(qt&ct)/max(1,len(qt)); q=float(ev.metadata.get('quality_score') or .5); trust=float(ev.metadata.get('trust_score') or .5)
    ev.score=round(WEIGHTS.get(ev.channel,WEIGHTS.get(ev.layer or '',.6))*.18 + lex*.42 + q*.20 + trust*.12 + ev.score*.08,4)
    ev.why_selected += [f'channel={ev.channel}', f'lexical_overlap={lex:.2f}', f'quality={q:.2f}', f'trust={trust:.2f}']
    return ev.score

def arbitrate_v4(query:str, channels:dict[str,list[dict[str,Any]]], limit:int=10)->dict[str,Any]:
    selected=[]; excluded=[]; seen=set(); votes={}
    for channel, rows in channels.items():
        votes[channel]=len(rows)
        for i,r in enumerate(rows):
            content=r.get('content') or r.get('text') or ''
            mid=r.get('id') or r.get('memory_id') or f'{channel}:{i}'
            key=r.get('content_hash') or (mid if mid else content[:200])
            if key in seen:
                excluded.append({'id':mid,'channel':channel,'reason':'duplicate_evidence'}); continue
            seen.add(key)
            meta=dict(r.get('metadata') or {})
            for k in ['quality_score','trust_score']:
                if k in r and k not in meta: meta[k]=r[k]
            ev=RecallEvidence(id=f'{channel}:{i}',channel=channel,content=content,memory_id=mid,layer=r.get('layer'),citation=r.get('source') or mid,metadata=meta)
            score(query, ev); selected.append(ev)
    selected.sort(key=lambda e:e.score, reverse=True)
    dec=RecallDecision(query, selected[:limit], excluded[:100], votes, selected[0].score if selected else 0.0)
    out=dec.to_dict(); out['winner_policy']='arbitration_v4'; out['why']='ranked by channel weight + lexical overlap + quality + trust + upstream score'; return out
