"""Bounded, read-only operational SLO snapshot generation."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

DEFAULT_THRESHOLDS={"canonical_projection_lag_seconds":300,"vector_index_age_seconds":3600,"stale_orphan_count":0,"conflict_oldest_age_seconds":86400,"quarantine_backlog":10,"correction_rate":0.05,"fallback_rate":0.05,"empty_success_rate":0.01,"recall_p95_ms":750}

def _tables(c): return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 500")}
def _cols(c,t): return {r[1] for r in c.execute("SELECT * FROM pragma_table_info(?)", (t,))}
def _age(value, now):
    if not value:return None
    try:return max(0,(now-datetime.fromisoformat(str(value).replace('Z','+00:00'))).total_seconds())
    except (ValueError,TypeError):return None
def _pct(vals,p):
    if not vals:return None
    vals=sorted(vals); return vals[min(len(vals)-1,max(0,int((len(vals)-1)*p+0.5)))]

def snapshot(db_path: str|Path, *, vector_path: str|Path|None=None, window_hours:int=24, limit:int=10000, thresholds:dict|None=None, now:datetime|None=None)->dict[str,Any]:
    if not 1<=window_hours<=24*30 or not 1<=limit<=50000: raise ValueError("bounded window/limit exceeded")
    now=now or datetime.now(timezone.utc); cutoff=(now-timedelta(hours=window_hours)).isoformat(); metrics={k:None for k in DEFAULT_THRESHOLDS}
    path=Path(db_path)
    if not path.is_file(): return {"status":"critical","alerts":["database_missing"],"bounded":{"window_hours":window_hours,"row_limit":limit},"metrics":metrics}
    con=sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro",uri=True); con.row_factory=sqlite3.Row
    try:
      tabs=_tables(con)
      if 'memories' in tabs:
        cols=_cols(con,'memories')
        if {'layer','created_at'}<=cols:
          latest=con.execute("SELECT MAX(created_at) FROM memories WHERE layer='workspace_markdown'").fetchone()[0]
          projected=con.execute("SELECT MAX(created_at) FROM memories WHERE layer!='workspace_markdown'").fetchone()[0]
          a,b=_age(latest,now),_age(projected,now); metrics['canonical_projection_lag_seconds']=max(0,(b or 0)-(a or 0)) if a is not None and b is not None else None
        stale_count=0
        if 'pending_canonical_sync' in cols:
          stale_count += con.execute("SELECT COUNT(*) FROM memories WHERE pending_canonical_sync=1").fetchone()[0]
        if 'soft_deleted' in cols:
          stale_count += con.execute("SELECT COUNT(*) FROM memories WHERE soft_deleted=1").fetchone()[0]
        metrics['stale_orphan_count']=stale_count
      if 'conflicts' in tabs:
        cols=_cols(con,'conflicts')
        if 'created_at' in cols and 'status' in cols:
          oldest=con.execute("SELECT MIN(created_at) FROM conflicts WHERE status NOT IN ('resolved','closed')").fetchone()[0]
        elif 'created_at' in cols:
          oldest=con.execute("SELECT MIN(created_at) FROM conflicts").fetchone()[0]
        else:
          oldest=None
        metrics['conflict_oldest_age_seconds']=_age(oldest,now) or 0
      if 'quarantine' in tabs:
        metrics['quarantine_backlog']=con.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
      elif 'quarantined_memories' in tabs:
        metrics['quarantine_backlog']=con.execute("SELECT COUNT(*) FROM quarantined_memories").fetchone()[0]
      else:
        metrics['quarantine_backlog']=0
      if 'telemetry_events' in tabs:
        rows=con.execute("SELECT kind,success,duration_ms,detail_json FROM telemetry_events WHERE created_at>=? ORDER BY created_at DESC LIMIT ?",(cutoff,limit)).fetchall()
        recalls=[r for r in rows if r['kind'] in ('recall','recall_result')]; durations=[float(r['duration_ms']) for r in recalls if r['duration_ms'] is not None]
        details=[]
        for r in recalls:
          try: details.append(json.loads(r['detail_json'] or '{}'))
          except Exception: details.append({})
        n=max(1,len(recalls)); metrics.update(recall_p50_ms=_pct(durations,.50),recall_p95_ms=_pct(durations,.95),fallback_rate=sum(bool(d.get('fallback')) for d in details)/n,empty_success_rate=sum(bool(r['success']) and bool(d.get('empty')) for r,d in zip(recalls,details))/n)
      if 'recall_events' in tabs:
        cols=_cols(con,'recall_events'); total=con.execute("SELECT COUNT(*) FROM recall_events LIMIT ?",(limit,)).fetchone()[0]
        if 'outcome' in cols: corrected=con.execute("SELECT COUNT(*) FROM recall_events WHERE outcome='corrected' LIMIT ?",(limit,)).fetchone()[0]
        elif 'event_type' in cols: corrected=con.execute("SELECT COUNT(*) FROM recall_events WHERE event_type='correction' LIMIT ?",(limit,)).fetchone()[0]
        else: corrected=0
        metrics['correction_rate']=corrected/max(1,total)
    finally: con.close()
    vp=Path(vector_path) if vector_path else path.parent/'vectors.sqlite3'; metrics['vector_index_age_seconds']=_age(datetime.fromtimestamp(vp.stat().st_mtime,timezone.utc).isoformat(),now) if vp.is_file() else None
    limits={**DEFAULT_THRESHOLDS,**(thresholds or {})}; alerts=[]
    for key,threshold in limits.items():
      value=metrics.get(key)
      if value is not None and value>threshold: alerts.append(key)
    status='critical' if any(a in alerts for a in ('canonical_projection_lag_seconds','stale_orphan_count','recall_p95_ms')) else ('warning' if alerts else 'ok')
    return {"status":status,"generated_at":now.isoformat(),"alerts":alerts,"bounded":{"window_hours":window_hours,"row_limit":limit},"metrics":metrics,"thresholds":limits}
