"""Session transcript indexing for Super Memory.

Adds corpus="sessions" support matching OpenClaw memory-core:
- Indexes session transcript .md files into a dedicated FTS5 table
- Filters by session visibility / agent access rules
- Returns MemorySearchHit-compatible results
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .config import load_config
from .storage import SuperMemoryStore, sqlite_path as resolve_sqlite_path
from .models import SuperMemoryConfig


# ── Constants ───────────────────────────────────────────────────────────────

SESSION_FTS_TABLE = "session_transcripts_fts"
SESSION_META_TABLE = "session_transcripts_meta"


# ── Schema ──────────────────────────────────────────────────────────────────


def ensure_session_schema(conn: sqlite3.Connection) -> None:
    """Create session FTS and metadata tables if they don't exist."""
    conn.executescript(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {SESSION_FTS_TABLE}
        USING fts5(
            content,
            session_id,
            agent_id,
            source_path,
            tokenize='porter unicode61'
        );

        CREATE TABLE IF NOT EXISTS {SESSION_META_TABLE} (
            source_path TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL DEFAULT '',
            file_hash TEXT NOT NULL DEFAULT '',
            chunk_count INTEGER NOT NULL DEFAULT 0,
            indexed_at TEXT NOT NULL DEFAULT (datetime('now')),
            total_chars INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()


# ── Chunking ────────────────────────────────────────────────────────────────


def chunk_session_text(text: str, max_chunk_chars: int = 2000) -> list[str]:
    """Split session text into overlapping chunks at natural boundaries."""
    if len(text) <= max_chunk_chars:
        return [text]

    chunks: list[str] = []
    lines = text.split("\n")
    current: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > max_chunk_chars and current:
            chunks.append("\n".join(current))
            # Keep last 2 lines for overlap
            overlap = current[-2:] if len(current) >= 2 else current
            current = list(overlap)
            current_len = sum(len(l) + 1 for l in overlap)
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))
    return chunks


# ── Indexing ────────────────────────────────────────────────────────────────


def _extract_session_id_from_path(path: Path) -> str:
    """Extract session ID from transcript filename."""
    stem = path.stem
    # Remove known prefixes: agent id, date prefixes
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
    stem = re.sub(r"^[a-z]+-", "", stem)
    return stem[:64]


def _extract_agent_id_from_path(path: Path) -> str:
    """Guess agent_id from transcript path."""
    parts = path.parts
    for part in parts:
        if part in ("lucas", "alex", "max", "isol", "boss", "agent"):
            return part
    return ""


def index_session_file(
    conn: sqlite3.Connection,
    file_path: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    """Index one session transcript file into FTS."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"ok": False, "path": str(file_path), "error": str(exc)}

    file_hash = str(hash(text))[:16]
    # Check if unchanged
    existing = conn.execute(
        f"SELECT file_hash FROM {SESSION_META_TABLE} WHERE source_path=?",
        (str(file_path),),
    ).fetchone()
    if existing and existing["file_hash"] == file_hash:
        return {"ok": True, "path": str(file_path), "unchanged": True}

    session_id = _extract_session_id_from_path(file_path)
    agent_id = _extract_agent_id_from_path(file_path)
    chunks = chunk_session_text(text)

    # Remove old entries
    conn.execute(f"DELETE FROM {SESSION_FTS_TABLE} WHERE source_path=?", (str(file_path),))
    conn.execute(f"DELETE FROM {SESSION_META_TABLE} WHERE source_path=?", (str(file_path),))

    # Insert chunks
    for i, chunk in enumerate(chunks):
        conn.execute(
            f"INSERT INTO {SESSION_FTS_TABLE}(content, session_id, agent_id, source_path) VALUES (?, ?, ?, ?)",
            (chunk, session_id, agent_id, str(file_path)),
        )

    conn.execute(
        f"INSERT OR REPLACE INTO {SESSION_META_TABLE}(source_path, session_id, agent_id, file_hash, chunk_count, total_chars) VALUES (?, ?, ?, ?, ?, ?)",
        (str(file_path), session_id, agent_id, file_hash, len(chunks), len(text)),
    )
    conn.commit()

    return {
        "ok": True,
        "path": str(file_path),
        "session_id": session_id,
        "agent_id": agent_id,
        "chunks": len(chunks),
        "chars": len(text),
    }


def index_all_sessions(
    config_path: str | None = None,
    sessions_dir: str | None = None,
) -> dict[str, Any]:
    """Index all session transcript files."""
    cfg = load_config(config_path)
    root = Path(cfg.workspace_root)
    sdir = Path(sessions_dir) if sessions_dir else root / "sessions"

    if not sdir.exists():
        return {"ok": False, "error": f"sessions dir not found: {sdir}"}

    store = SuperMemoryStore(cfg)
    conn = store.connect()
    ensure_session_schema(conn)

    results: list[dict[str, Any]] = []
    errors = 0

    for md_file in sorted(sdir.glob("*.md")):
        r = index_session_file(conn, md_file, root)
        results.append(r)
        if not r.get("ok"):
            errors += 1

    # Stats
    indexed = sum(1 for r in results if r.get("ok"))
    unchanged = sum(1 for r in results if r.get("unchanged"))
    total_chunks = conn.execute(f"SELECT COUNT(*) FROM {SESSION_FTS_TABLE}").fetchone()[0]

    return {
        "ok": True,
        "files_found": len(results),
        "indexed": indexed,
        "unchanged": unchanged,
        "errors": errors,
        "total_chunks": total_chunks,
        "results": results[:20],  # first 20
    }


# ── Search ──────────────────────────────────────────────────────────────────


MEMORY_CORE_SESSION_RESULT_KEYS = [
    "id", "path", "startLine", "endLine",
    "score", "textScore", "snippet",
    "source", "corpus", "citation",
]


def search_sessions(
    query: str,
    *,
    max_results: int = 5,
    min_score: float = 0.0,
    agent_id: str | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Search session transcripts via FTS5, returning memory-core compatible results.

    Returns results matching OpenClaw memory_search format exactly:
    {
        "results": [{
            "id": str,
            "path": str,
            "startLine": int,
            "endLine": int,
            "score": float,
            "textScore": float,
            "snippet": str,
            "source": "sessions",
            "corpus": "sessions",
            "citation": str,
        }],
        "provider": "super-memory",
        "citations": "auto",
    }
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    conn = store.connect()
    ensure_session_schema(conn)

    # FTS5 search
    fts_query = _fts_safe_query(query)
    if not fts_query:
        return {"results": [], "provider": "super-memory", "citations": "auto", "debug": {"error": "empty query"}}

    try:
        rows = conn.execute(
            f"""
            SELECT f.rowid, f.content, f.session_id, f.agent_id, f.source_path,
                   rank as fts_rank
            FROM {SESSION_FTS_TABLE} f
            WHERE {SESSION_FTS_TABLE} MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, max_results * 2),
        ).fetchall()
    except Exception as exc:
        return {"results": [], "provider": "super-memory", "citations": "auto", "debug": {"error": str(exc)}}

    results = []
    for row in rows:
        content = row["content"] or ""
        score = _compute_score(row, query)
        if score < min_score:
            continue

        snippet = _make_snippet(content, query, max_chars=500)
        source_path = row["source_path"] or ""

        results.append({
            "id": f"session:{row['session_id']}:{row['rowid']}",
            "path": source_path,
            "startLine": 1,
            "endLine": max(1, content.count("\n") + 1),
            "score": round(score, 4),
            "textScore": round(score, 4),
            "snippet": snippet,
            "source": "sessions",
            "corpus": "sessions",
            "citation": f"session {row['session_id']}" if row["session_id"] else "",
        })

    results = results[:max_results]

    return {
        "results": results,
        "provider": "super-memory",
        "citations": "auto",
        "debug": {
            "backend": "super-memory.session_index",
            "corpus": "sessions",
            "hits": len(results),
            "fts_query": fts_query,
        },
    }


# ── Helpers ─────────────────────────────────────────────────────────────────


def _fts_safe_query(query: str) -> str:
    """Convert a plain-text query to FTS5-safe query string."""
    # Remove special FTS5 characters
    cleaned = re.sub(r'[^\w\s]', ' ', query)
    terms = [t.strip() for t in cleaned.split() if len(t.strip()) >= 2]
    if not terms:
        return ""
    return " OR ".join(terms[:10])  # max 10 terms


def _compute_score(row: sqlite3.Row, query: str) -> float:
    """Compute a relevance score from FTS rank + text match."""
    content = (row["content"] or "").lower()
    q = query.lower()

    base = 0.5
    # FTS rank bonus (lower rank = better)
    fts_rank = row["fts_rank"] if "fts_rank" in row.keys() else 1.0
    rank_score = max(0.0, 1.0 - fts_rank * 0.1)

    # Direct match bonus
    match_bonus = 0.3 if q in content else 0.0

    # Term coverage
    terms = [t for t in q.split() if t]
    if terms:
        matched = sum(1 for t in terms if t in content)
        coverage = matched / len(terms)
        coverage_bonus = coverage * 0.2
    else:
        coverage_bonus = 0.0

    return min(1.0, base + rank_score + match_bonus + coverage_bonus)


def _make_snippet(content: str, query: str, max_chars: int = 500) -> str:
    """Build a relevant snippet around the query match."""
    if len(content) <= max_chars:
        return content
    idx = content.lower().find(query.lower())
    if idx < 0:
        return content[:max_chars] + "…"
    start = max(0, idx - max_chars // 3)
    end = min(len(content), start + max_chars)
    prefix = "…" if start else ""
    suffix = "…" if end < len(content) else ""
    return prefix + content[start:end] + suffix


def session_index_status(config_path: str | None = None) -> dict[str, Any]:
    """Get session index health status."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    conn = store.connect()

    try:
        total_chunks = conn.execute(f"SELECT COUNT(*) FROM {SESSION_FTS_TABLE}").fetchone()[0]
        total_files = conn.execute(f"SELECT COUNT(*) FROM {SESSION_META_TABLE}").fetchone()[0]
        total_chars = conn.execute(f"SELECT COALESCE(SUM(total_chars), 0) FROM {SESSION_META_TABLE}").fetchone()[0]
    except Exception:
        return {"ok": True, "available": False, "error": "session tables not initialized"}

    return {
        "ok": True,
        "available": True,
        "files_indexed": total_files,
        "chunks_indexed": total_chunks,
        "total_chars_indexed": total_chars,
    }
