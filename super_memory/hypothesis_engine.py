"""Grounded, reconstructable hypothesis and evidence ledger."""
from __future__ import annotations
import hashlib, json, math, uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

def _now(): return datetime.now(timezone.utc).isoformat()
@dataclass
class Hypothesis:
    id:str; content:str; confidence:float=.5; status:str="active"; tags:list[str]=field(default_factory=list); evidence_ids:list[str]=field(default_factory=list); created_at:str=""; updated_at:str=""; superseded_by:str|None=None; version:int=1
@dataclass
class EvidenceItem:
    id:str; hypothesis_id:str; content:str; direction:str; source_id:str; weight:float=.5; source_trust:float=.5; content_hash:str=""; created_at:str=""
class HypothesisEngine:
    def __init__(self, state:dict[str,Any]|None=None):
        self._hypotheses={}; self._evidence={}; self._hypo_evidence={}; self._dedup=set()
        if state: self.load_save_dict(state)
    def create_hypothesis(self,content,confidence=.5,tags=None):
        if not str(content).strip(): raise ValueError("hypothesis content is required")
        if not isinstance(confidence,(int,float)) or not math.isfinite(confidence): raise ValueError("confidence must be finite")
        now=_now(); h=Hypothesis(str(uuid.uuid4()),str(content).strip(),max(.01,min(.99,float(confidence))),tags=list(tags or []),created_at=now,updated_at=now); self._hypotheses[h.id]=h; self._hypo_evidence[h.id]=h.evidence_ids; return h
    def add_evidence(self,hypothesis_id,content,direction="for",weight=.5,*,source_id=None,source_trust=.5):
        h=self._hypotheses.get(hypothesis_id)
        if not h or h.status=="superseded": return None
        if direction not in {"for","against"}: raise ValueError("direction must be 'for' or 'against'")
        if not source_id or not str(source_id).strip(): raise ValueError("source_id is required")
        for name,val in (("weight",weight),("source_trust",source_trust)):
            if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val) or not 0 < val <= 1: raise ValueError(f"{name} must be finite and in (0, 1]")
        body=str(content).strip(); digest=hashlib.sha256(body.casefold().encode()).hexdigest(); key=(hypothesis_id,str(source_id),digest,direction)
        if not body: raise ValueError("evidence content is required")
        if key in self._dedup: return None
        ev=EvidenceItem(str(uuid.uuid4()),hypothesis_id,body,direction,str(source_id),float(weight),float(source_trust),digest,_now()); self._evidence[ev.id]=ev; self._dedup.add(key); h.evidence_ids.append(ev.id)
        effective=ev.weight*ev.source_trust
        h.confidence = h.confidence+(1-h.confidence)*effective*.3 if direction=="for" else h.confidence*(1-effective*.5)
        h.confidence=max(.01,min(.99,h.confidence)); h.updated_at=_now()
        independent={self._evidence[e].source_id for e in h.evidence_ids if self._evidence[e].direction==direction and self._evidence[e].source_trust>=.5}
        if h.confidence>=.9 and len(independent)>=3: h.status="confirmed"
        elif h.confidence<=.1 and len(independent)>=3: h.status="refuted"
        elif h.status in {"confirmed","refuted"}: h.status="challenged"
        return ev
    def evolve_hypothesis(self,hypothesis_id,new_content,reason=""):
        old=self._hypotheses.get(hypothesis_id)
        if not old:return None
        new=self.create_hypothesis(new_content,old.confidence,old.tags.copy()); new.version=old.version+1; new.evidence_ids=old.evidence_ids.copy(); self._hypo_evidence[new.id]=new.evidence_ids; old.status="superseded"; old.superseded_by=new.id; old.updated_at=_now()
        if reason:self.add_evidence(new.id,f"Evolution rationale: {reason}","for",.4,source_id=f"hypothesis:{old.id}",source_trust=1)
        return new
    def get_hypothesis(self,i):return self._hypotheses.get(i)
    def get_evidence(self,i):return [self._evidence[x] for x in self._hypotheses.get(i,Hypothesis('', '')).evidence_ids if x in self._evidence]
    def list_hypotheses(self,status=None):return [h for h in self._hypotheses.values() if status is None or h.status==status]
    def to_save_dict(self): return {"schema_version":2,"hypotheses":{k:asdict(v) for k,v in self._hypotheses.items()},"evidence":{k:asdict(v) for k,v in self._evidence.items()}}
    def load_save_dict(self,state):
        for k,v in state.get("hypotheses",{}).items(): self._hypotheses[k]=Hypothesis(id=k,**{x:y for x,y in v.items() if x!='id'}); self._hypo_evidence[k]=self._hypotheses[k].evidence_ids
        for k,v in state.get("evidence",{}).items():
            e=EvidenceItem(id=k,**{x:y for x,y in v.items() if x!='id'}); self._evidence[k]=e; self._dedup.add((e.hypothesis_id,e.source_id,e.content_hash,e.direction))
_engine=None
def get_engine():
 global _engine
 if _engine is None:_engine=HypothesisEngine()
 return _engine
