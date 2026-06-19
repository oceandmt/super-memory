from __future__ import annotations

import json
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any

from .config import load_config
from .models import SuperMemoryConfig
from .vector import VectorStore, embed_text


def _sqlite_vec_available() -> bool:
    try:
        import sqlite_vec  # noqa: F401
        return True
    except Exception:
        return False


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    import sqlite_vec

    conn.enable_load_extension(True)
    sqlite_vec.load(conn)


def _ollama_embed_batch(texts: list[str], cfg: SuperMemoryConfig) -> list[list[float]]:
    endpoint = getattr(cfg, "embedding_endpoint", "http://127.0.0.1:11434/api/embed")
    model = getattr(cfg, "embedding_model", "nomic-embed-text")
    payload = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    embeddings = data.get("embeddings") or []
    if len(embeddings) != len(texts):
        raise RuntimeError(f"embedding count mismatch: expected {len(texts)}, got {len(embeddings)}")
    return [list(vec) for vec in embeddings]


def semantic_doctor(config_path: str | None = None, query: str = "semantic recall smoke test") -> dict[str, Any]:
    cfg = load_config(config_path)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any = None, severity: str = "error") -> None:
        checks.append({"name": name, "ok": bool(ok), "severity": severity, "detail": detail})

    add("vector_enabled", bool(cfg.vector_enabled), {"vector_enabled": cfg.vector_enabled})
    add("embedding_provider", getattr(cfg, "embedding_provider", "") == "ollama", {"provider": getattr(cfg, "embedding_provider", None)})
    add("sqlite_vec_installed", _sqlite_vec_available())

    vec_path = Path(cfg.workspace_root) / "data" / "vectors.sqlite3"
    add("vector_db_exists", vec_path.exists(), {"path": str(vec_path)}, severity="warning")

    db_path = Path(cfg.workspace_root) / cfg.sqlite_path
    add("memory_db_exists", db_path.exists(), {"path": str(db_path)})

    embed_ok = False
    embed_dim = None
    try:
        vec = embed_text(query, config=cfg)
        embed_ok = vec is not None
        embed_dim = len(vec) if vec else None
    except Exception as exc:  # pragma: no cover - defensive
        add("ollama_embedding", False, str(exc))
    else:
        add("ollama_embedding", embed_ok, {"model": cfg.embedding_model, "dimension": embed_dim})
        if embed_ok:
            add("embedding_dimension_matches_config", embed_dim == cfg.embedding_dimension, {"actual": embed_dim, "config": cfg.embedding_dimension})

    vector_count = 0
    if vec_path.exists() and _sqlite_vec_available():
        try:
            conn = sqlite3.connect(str(vec_path))
            _load_sqlite_vec(conn)
            vector_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            conn.close()
            add("vector_rows", vector_count > 0, {"count": vector_count}, severity="warning")
        except Exception as exc:
            add("vector_rows", False, str(exc), severity="warning")

    ok = all(c["ok"] or c["severity"] == "warning" for c in checks)
    return {
        "ok": ok,
        "verdict": "pass" if ok else "fail",
        "config_path": config_path,
        "workspace_root": str(cfg.workspace_root),
        "vector_db": str(vec_path),
        "vector_count": vector_count,
        "checks": checks,
    }


def semantic_index(
    config_path: str | None = None,
    *,
    rebuild: bool = False,
    batch_size: int = 8,
    limit: int | None = None,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    if not _sqlite_vec_available():
        return {"ok": False, "error": "sqlite-vec is not installed. Install with: pip install super-memory[semantic] or pip install sqlite-vec"}
    if getattr(cfg, "embedding_provider", "ollama") != "ollama":
        return {"ok": False, "error": f"unsupported embedding_provider: {cfg.embedding_provider}"}

    db_path = Path(cfg.workspace_root) / cfg.sqlite_path
    vec_path = Path(cfg.workspace_root) / "data" / "vectors.sqlite3"
    vec_path.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(str(db_path))
    source.row_factory = sqlite3.Row
    rows = source.execute(
        "SELECT id, content FROM memories WHERE layer='workspace_markdown' ORDER BY rowid"
    ).fetchall()
    source.close()
    if limit is not None:
        rows = rows[:limit]

    conn = sqlite3.connect(str(vec_path))
    _load_sqlite_vec(conn)
    if rebuild:
        conn.execute("DROP TABLE IF EXISTS embeddings")
    conn.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS embeddings
        USING vec0(memory_id TEXT PRIMARY KEY, embedding FLOAT[{int(cfg.embedding_dimension)}])
        """
    )
    conn.commit()
    existing = set(r[0] for r in conn.execute("SELECT memory_id FROM embeddings").fetchall())
    pending = [(r["id"], r["content"] or "") for r in rows if rebuild or r["id"] not in existing]

    indexed = 0
    failed: list[dict[str, str]] = []
    for i in range(0, len(pending), max(1, batch_size)):
        chunk = pending[i : i + max(1, batch_size)]
        ids = [mid for mid, _ in chunk]
        texts = [text for _, text in chunk]
        try:
            vectors = _ollama_embed_batch(texts, cfg)
            for mid, vector in zip(ids, vectors):
                conn.execute("INSERT OR REPLACE INTO embeddings (memory_id, embedding) VALUES (?, ?)", (mid, json.dumps(vector)))
            conn.commit()
            indexed += len(chunk)
        except Exception as exc:
            for mid, text in chunk:
                try:
                    vector = _ollama_embed_batch([text], cfg)[0]
                    conn.execute("INSERT OR REPLACE INTO embeddings (memory_id, embedding) VALUES (?, ?)", (mid, json.dumps(vector)))
                    conn.commit()
                    indexed += 1
                except Exception as item_exc:  # pragma: no cover - depends on local runtime
                    failed.append({"memory_id": mid, "error": str(item_exc or exc)})

    total_vectors = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    conn.close()
    return {
        "ok": len(failed) == 0,
        "source_rows": len(rows),
        "already_indexed": len(existing) if not rebuild else 0,
        "pending": len(pending),
        "indexed": indexed,
        "failed": failed,
        "vector_count": total_vectors,
        "vector_db": str(vec_path),
    }


def semantic_verify(config_path: str | None = None, query: str = "semantic recall smoke test", limit: int = 5) -> dict[str, Any]:
    cfg = load_config(config_path)
    store = VectorStore(cfg)
    results = store.search_text(query, top_k=limit)
    hydrated: list[dict[str, Any]] = []
    if results:
        db_path = Path(cfg.workspace_root) / cfg.sqlite_path
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        for memory_id, score in results:
            row = conn.execute(
                "SELECT id, content, type, agent_id, session_id, created_at FROM memories WHERE id=? AND layer='workspace_markdown'",
                (memory_id,),
            ).fetchone()
            if row:
                item = dict(row)
                item["semantic_score"] = score
                item["provenance"] = {"layer": "semantic", "id": memory_id}
                hydrated.append(item)
        conn.close()
    return {
        "ok": bool(hydrated),
        "query": query,
        "count": len(hydrated),
        "results": hydrated,
    }
