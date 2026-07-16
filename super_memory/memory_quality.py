"""Server-authoritative semantic quality, completeness, trust and evidence."""
from __future__ import annotations
import json, re, sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
from .quality_scorer import score_memory
QUALITY_CONTRACT_VERSION = "2.0"
QUALITY_MODEL_VERSION = "3.0"
QUALITY_WEIGHTS = {"content_quality":.30,"completeness":.25,"source_trust":.20,"extraction_confidence":.15,"freshness":.10}
_TYPE_REQUIREMENTS={"todo":("action","status"),"decision":("decision","rationale"),"fact":("subject","evidence"),"preference":("subject","preference"),"blocker":("blocked_item","cause"),"event":("event_time","participants")}
_HINTS={"action":re.compile(r"\b(todo|need to|must|should|action|implement|fix)\b",re.I),"status":re.compile(r"\b(pending|done|complete|blocked|in progress|open)\b",re.I),"decision":re.compile(r"\b(decid(?:e|ed|ion)|chosen|use|adopt)\b",re.I),"rationale":re.compile(r"\b(because|so that|reason|therefore|due to)\b",re.I),"subject":re.compile(r"\b[A-Za-z][\w./:-]{2,}\b"),"evidence":re.compile(r"\b(source|evidence|observed|according|tested|verified|https?://)\b",re.I),"preference":re.compile(r"\b(prefer|like|avoid|default|want)\b",re.I),"blocked_item":re.compile(r"\b(blocked|blocker|cannot|can't|failed)\b",re.I),"cause":re.compile(r"\b(because|caused by|due to|reason|depends on)\b",re.I),"event_time":re.compile(r"\b(20\d\d[-/]\d\d[-/]\d\d|today|yesterday|tomorrow|at \d{1,2}:\d{2})\b",re.I),"participants":re.compile(r"\b(by|with|from|user|boss|agent|team|alice|bob)\b",re.I)}
@dataclass(frozen=True)
class CompletenessResult: score:float; present:tuple[str,...]; missing:tuple[str,...]; schema_version:str="1"
def evaluate_completeness(content:str,memory_type:str,metadata:dict[str,Any]|None=None)->CompletenessResult:
 meta=metadata or {}; required=_TYPE_REQUIREMENTS.get(str(memory_type).lower(),("subject","evidence")); present=[]; missing=[]
 for field in required:(present if meta.get(field) not in (None,"",[],{}) or _HINTS[field].search(content or "") else missing).append(field)
 return CompletenessResult(round(len(present)/len(required),4),tuple(present),tuple(missing))
def _clamp(value:Any,default:float)->float:
 try:return round(max(0.,min(1.,float(value))),4)
 except (TypeError,ValueError):return default
def authoritative_quality(content:str,memory_type:str,metadata:dict[str,Any]|None=None,source:str|None=None)->dict[str,Any]:
 meta=metadata or {}; legacy=score_memory(content,memory_type); complete=evaluate_completeness(content,memory_type,meta)
 source_trust=_clamp(meta.get("source_trust", .8 if source or meta.get("source") else .5),.5)
 extraction=_clamp(meta.get("extraction_confidence",meta.get("semantic_classification",{}).get("confidence",.75)),.75)
 freshness=_clamp(meta.get("freshness",1.0),1.0)
 components={"content_quality":_clamp(legacy.overall,.5),"completeness":complete.score,"source_trust":source_trust,"extraction_confidence":extraction,"freshness":freshness}
 overall=round(sum(components[k]*QUALITY_WEIGHTS[k] for k in QUALITY_WEIGHTS),4)
 return {"version":QUALITY_CONTRACT_VERSION,"model_version":QUALITY_MODEL_VERSION,"overall":overall,"components":components,"weights":QUALITY_WEIGHTS.copy(),"warnings":list(legacy.warnings),"legacy":{"fidelity":round(legacy.fidelity,4),"sufficiency":round(legacy.sufficiency,4),"importance":round(legacy.importance,4)}}
def enrich_quality_metadata(content:str,memory_type:str,metadata:dict[str,Any]|None=None,source:str|None=None)->dict[str,Any]:
 out=dict(metadata or {}); q=authoritative_quality(content,memory_type,out,source); c=evaluate_completeness(content,memory_type,out)
 # One score, several compatibility views.
 out["quality"]=q; out["quality_score"]=q["overall"]; out["completeness"]=asdict(c)
 out["quality"].update(q["legacy"]); return out
def ensure_quality_tables(conn):
 conn.executescript("""CREATE TABLE IF NOT EXISTS memory_evidence(id INTEGER PRIMARY KEY AUTOINCREMENT,memory_id TEXT NOT NULL,evidence_memory_id TEXT NOT NULL,relation TEXT NOT NULL DEFAULT 'supports',quote TEXT,confidence REAL NOT NULL DEFAULT .5,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(memory_id,evidence_memory_id,relation));CREATE INDEX IF NOT EXISTS idx_memory_evidence_memory ON memory_evidence(memory_id);CREATE TABLE IF NOT EXISTS memory_quality_events(id INTEGER PRIMARY KEY AUTOINCREMENT,memory_id TEXT NOT NULL,event_type TEXT NOT NULL,score REAL,payload_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);""")
def evolve_trust(conn,memory_id):
 ensure_quality_tables(conn); conn.row_factory=sqlite3.Row; row=conn.execute("SELECT trust_score,metadata_json FROM memories WHERE id=?",(memory_id,)).fetchone()
 if not row:return {"ok":False,"error":"memory_not_found","memory_id":memory_id}
 try:meta=json.loads(row["metadata_json"] or "{}")
 except json.JSONDecodeError:meta={}
 quality=float(meta.get("quality_score",.5)); evidence=conn.execute("SELECT COUNT(*) FROM memory_evidence WHERE memory_id=? AND relation='supports'",(memory_id,)).fetchone()[0]; conflicts=conn.execute("SELECT COUNT(*) FROM memory_evidence WHERE memory_id=? AND relation='contradicts'",(memory_id,)).fetchone()[0]; score=round(max(.05,min(1,.25+quality*.5+min(evidence,5)*.03+(.08 if meta.get("canonical") else 0)-min(conflicts,5)*.08)),4); meta["trust"]={"version":"1","score":score,"evidence_count":evidence,"conflict_count":conflicts,"updated_at":datetime.now(timezone.utc).isoformat()}; conn.execute("UPDATE memories SET trust_score=?,metadata_json=? WHERE id=?",(score,json.dumps(meta),memory_id)); return {"ok":True,"memory_id":memory_id,"trust_score":score,**meta["trust"]}
def build_evidence_chain(conn,memory_id,max_depth=3):
 ensure_quality_tables(conn); conn.row_factory=sqlite3.Row; root=conn.execute("SELECT id,content,trust_score,source,created_at FROM memories WHERE id=?",(memory_id,)).fetchone()
 if not root:return {"ok":False,"error":"memory_not_found","memory_id":memory_id}
 visited={memory_id}; frontier=[(memory_id,0)]; edges=[]; nodes={memory_id:dict(root)}
 while frontier:
  current,depth=frontier.pop(0)
  if depth>=max(0,min(max_depth,8)):continue
  for edge in conn.execute("SELECT * FROM memory_evidence WHERE memory_id=? ORDER BY confidence DESC",(current,)).fetchall():
   item=dict(edge); edges.append(item); target=item["evidence_memory_id"]
   if target in visited:continue
   visited.add(target); linked=conn.execute("SELECT id,content,trust_score,source,created_at FROM memories WHERE id=?",(target,)).fetchone()
   if linked:nodes[target]=dict(linked); frontier.append((target,depth+1))
 support=sum(float(e["confidence"]) for e in edges if e["relation"]=="supports"); oppose=sum(float(e["confidence"]) for e in edges if e["relation"]=="contradicts"); confidence=round(max(0,min(1,(float(root["trust_score"] or .5)+support)/(1+support+oppose))),4); return {"ok":True,"memory_id":memory_id,"confidence":confidence,"nodes":list(nodes.values()),"edges":edges,"depth":max_depth}
def temporal_query(conn,start,end,entity=None,limit=100):
 conn.row_factory=sqlite3.Row; safe_limit=max(1,min(limit,1000))
 if entity:
  pattern=f"%{entity}%"; rows=conn.execute("SELECT * FROM memories WHERE created_at<=? AND COALESCE(json_extract(metadata_json,'$.valid_until'),'9999-12-31T23:59:59Z')>=? AND (content LIKE ? OR metadata_json LIKE ?) ORDER BY created_at DESC LIMIT ?",(end,start,pattern,pattern,safe_limit)).fetchall()
 else:
  rows=conn.execute("SELECT * FROM memories WHERE created_at<=? AND COALESCE(json_extract(metadata_json,'$.valid_until'),'9999-12-31T23:59:59Z')>=? ORDER BY created_at DESC LIMIT ?",(end,start,safe_limit)).fetchall()
 memories=[dict(r) for r in rows]; return {"ok":True,"start":start,"end":end,"entity":entity,"count":len(memories),"memories":memories}
