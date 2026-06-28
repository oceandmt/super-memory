from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .config import load_config
from .storage import SuperMemoryStore


def ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS maintenance_jobs (
          id TEXT PRIMARY KEY,
          job_type TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          args_json TEXT NOT NULL DEFAULT '{}',
          result_json TEXT,
          error TEXT,
          attempts INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          started_at TEXT,
          completed_at TEXT,
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_maintenance_jobs_status ON maintenance_jobs(status, job_type, created_at);
        """
    )


def enqueue(job_type: str, args: dict[str, Any] | None = None, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(args or {}, sort_keys=True, ensure_ascii=False)
    jid = "maint_" + hashlib.sha256(f"{job_type}:{payload}:{now}".encode()).hexdigest()[:24]
    with store.connect() as conn:
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO maintenance_jobs(id,job_type,status,args_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (jid, job_type, "pending", payload, now, now),
        )
    return {"ok": True, "job_id": jid, "status": "pending", "job_type": job_type}


def status(job_id: str, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    with store.connect() as conn:
        ensure_schema(conn)
        row = conn.execute("SELECT * FROM maintenance_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "job not found", "job_id": job_id}
    result = None
    if row["result_json"]:
        try: result = json.loads(row["result_json"])
        except Exception: result = {"raw": row["result_json"]}
    return {"ok": True, "job_id": job_id, "job_type": row["job_type"], "status": row["status"], "result": result, "error": row["error"], "updated_at": row["updated_at"]}


def _run(job_type: str, args: dict[str, Any], config_path: str | None = None) -> dict[str, Any]:
    if job_type == "deep_improve":
        from .deep_auto import deep_improve
        return deep_improve(dry_run=bool(args.get("dry_run", True)), config_path=config_path)
    if job_type == "self_heal_status_full":
        from .self_heal import self_heal_status
        return self_heal_status(config_path=config_path)
    if job_type == "self_heal_embeddings":
        from .self_heal import self_heal_embeddings
        return self_heal_embeddings(batch_size=int(args.get("batch_size", 100)), config_path=config_path)
    return {"ok": False, "error": f"unknown job_type: {job_type}"}


def process_jobs(limit: int = 5, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    processed = []
    with store.connect() as conn:
        ensure_schema(conn)
        jobs = conn.execute("SELECT * FROM maintenance_jobs WHERE status IN ('pending','retry') ORDER BY created_at ASC LIMIT ?", (limit,)).fetchall()
    for job in jobs:
        now = datetime.now(timezone.utc).isoformat()
        with store.connect() as conn:
            conn.execute("UPDATE maintenance_jobs SET status='running', started_at=COALESCE(started_at,?), updated_at=? WHERE id=?", (now, now, job["id"]))
        try:
            args = json.loads(job["args_json"] or "{}")
            result = _run(job["job_type"], args, config_path=config_path)
            done = datetime.now(timezone.utc).isoformat()
            with store.connect() as conn:
                conn.execute("UPDATE maintenance_jobs SET status='done', result_json=?, completed_at=?, updated_at=?, error=NULL WHERE id=?", (json.dumps(result, ensure_ascii=False), done, done, job["id"]))
            processed.append({"job_id": job["id"], "status": "done"})
        except Exception as exc:
            done = datetime.now(timezone.utc).isoformat()
            attempts = int(job["attempts"] or 0) + 1
            st = "failed" if attempts >= 3 else "retry"
            with store.connect() as conn:
                conn.execute("UPDATE maintenance_jobs SET status=?, attempts=?, error=?, updated_at=? WHERE id=?", (st, attempts, f"{type(exc).__name__}: {exc}", done, job["id"]))
            processed.append({"job_id": job["id"], "status": st})
    return {"ok": True, "processed": len(processed), "jobs": processed}


def deep_improve_mcp_safe(dry_run: bool = True, config_path: str | None = None, *, async_mode: bool = True, compact: bool = True, max_seconds: int = 3) -> dict[str, Any]:
    if async_mode:
        out = enqueue("deep_improve", {"dry_run": dry_run, "compact": compact}, config_path=config_path)
        out.update({"mode": "async", "message": "deep_improve queued; run maintenance_process_jobs then poll status"})
        return out
    from .deep_auto import deep_improve
    result = deep_improve(dry_run=dry_run, config_path=config_path)
    if compact:
        return {"ok": result.get("ok", True), "mode": "sync", "compact": True, "summary": result.get("summary"), "audit_grade": result.get("audit_grade"), "qualify_grade": result.get("qualify_grade"), "problems_found": result.get("problems_found"), "applied_count": len(result.get("applied", [])), "improvement_count": len(result.get("improvement_proposals", []))}
    return result
