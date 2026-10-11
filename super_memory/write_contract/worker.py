from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from ..config import load_config
from ..storage import SuperMemoryStore
from ..embeddings_registry import select_best_adapter
from ..vector import VectorStore
from .migrations import ensure_schema

logger = logging.getLogger(__name__)


def process_memory_jobs(limit: int = 50, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    adapter = select_best_adapter()
    if adapter is None:
        return {"ok": False, "error": "no embedding provider available", "processed": 0}
    # Authoritative semantic-recall store (data/vectors.sqlite3). The main DB's
    # memory_vectors table below is only a legacy compatibility cache; recall
    # reads from the VectorStore, so both must be written here.
    vector_store = VectorStore(cfg)
    processed = repaired = errors = 0
    authoritative_repaired = 0
    now = datetime.now(timezone.utc).isoformat()
    with store.connect() as conn:
        ensure_schema(conn)
        conn.execute("""CREATE TABLE IF NOT EXISTS memory_vectors (
            id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            memory_id TEXT NOT NULL,
            layer TEXT NOT NULL,
            vector TEXT NOT NULL,
            provider TEXT,
            dimensions INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(memory_id, layer)
        )""")
        jobs = conn.execute(
            """
            SELECT * FROM memory_jobs
            WHERE status IN ('pending','retry') AND job_type='embed'
              AND (next_run_at IS NULL OR next_run_at <= datetime('now'))
            ORDER BY created_at ASC LIMIT ?
            """,
            (limit,),
        ).fetchall()

        # Pass 1: resolve each job's source row; mark no-row jobs done; collect
        # the valid ones so we can embed them in batches (much faster on CPU).
        valid: list[tuple[Any, Any]] = []
        for job in jobs:
            processed += 1
            row = conn.execute(
                "SELECT id, layer, content FROM memories WHERE id=? AND layer=? AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0) != 1 LIMIT 1",
                (job["memory_id"], job["layer"]),
            ).fetchone()
            if not row or not row["content"]:
                conn.execute("UPDATE memory_jobs SET status='done', updated_at=? WHERE id=?", (now, job["id"]))
                continue
            valid.append((job, row))

        # Pass 2: batch-embed contents, then write both vector stores.
        EMBED_CHUNK = 16
        for start in range(0, len(valid), EMBED_CHUNK):
            chunk = valid[start:start + EMBED_CHUNK]
            try:
                vectors = adapter.embed_batch([str(r["content"]) for _, r in chunk])
            except Exception as exc:
                # Fall back to per-item so one bad content cannot fail the batch.
                vectors = []
                for _, r in chunk:
                    try:
                        vectors.append(adapter.embed(str(r["content"])))
                    except Exception:
                        vectors.append(None)
            for (job, row), vec in zip(chunk, vectors):
                try:
                    if vec is None:
                        raise RuntimeError("embedding failed for row")
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO memory_vectors (memory_id, layer, vector, provider, dimensions)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (row["id"], row["layer"], json.dumps(vec), adapter.name, len(vec)),
                    )
                    # Mirror into the authoritative vector store that recall reads.
                    try:
                        if vector_store.add_embedding(row["id"], vec):
                            authoritative_repaired += 1
                    except Exception as vec_exc:  # noqa: BLE001
                        logger.warning("authoritative vector write failed for %s: %s", row["id"], vec_exc)
                    conn.execute("UPDATE memory_jobs SET status='done', updated_at=?, last_error=NULL WHERE id=?", (now, job["id"]))
                    repaired += 1
                except Exception as exc:
                    errors += 1
                    attempts = int(job["attempts"] or 0) + 1
                    status = "failed" if attempts >= int(job["max_attempts"] or 5) else "retry"
                    conn.execute(
                        "UPDATE memory_jobs SET status=?, attempts=?, updated_at=?, last_error=? WHERE id=?",
                        (status, attempts, now, f"{type(exc).__name__}: {exc}", job["id"]),
                    )
    return {"ok": errors == 0, "processed": processed, "repaired": repaired, "authoritative_repaired": authoritative_repaired, "errors": errors, "provider": adapter.name}


def reconcile_memory_integrity(limit: int = 200, config_path: str | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    created_jobs = 0
    with store.connect() as conn:
        ensure_schema(conn)
        missing = conn.execute(
            """
            SELECT m.id, m.layer FROM memories m
            LEFT JOIN memory_vectors v ON v.memory_id=m.id AND v.layer=m.layer
            LEFT JOIN memory_jobs j ON j.memory_id=m.id AND j.layer=m.layer AND j.job_type='embed' AND j.status IN ('pending','retry','failed')
            WHERE m.content IS NOT NULL AND m.content != ''
              AND COALESCE(json_extract(m.metadata_json,'$.soft_deleted'),0) != 1
              AND v.id IS NULL AND j.id IS NULL
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        now = datetime.now(timezone.utc).isoformat()
        import hashlib
        for row in missing:
            jid = hashlib.sha256(f"{row['id']}:{row['layer']}:embed".encode()).hexdigest()
            conn.execute(
                "INSERT OR IGNORE INTO memory_jobs (id,memory_id,layer,job_type,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                (jid, row["id"], row["layer"], "embed", "pending", now, now),
            )
            created_jobs += 1
    return {"ok": True, "created_embed_jobs": created_jobs}
