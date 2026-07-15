"""Semantic Closets & Drawers — verbatim-preserving pointer layer.

Borrowed from MemPalace:
- drawers = raw canonical verbatim evidence (one per memory chunk)
- closets = compact semantic pointers with line offsets and drawer IDs
- recall = closet search → drawer hydration
- neighbor expansion protects against chunk boundary failures

Key property: canonical Workspace Markdown is NEVER modified by closets/drawers.
Closets are a derived read-only projection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from ..config import load_config
from ..storage import SuperMemoryStore, row_to_memory

logger = logging.getLogger("super-memory.projections.closet")

# ── Config ───────────────────────────────────────────────────────────────────

CHUNK_SIZE = 1024          # chars per drawer
CHUNK_OVERLAP = 128        # overlap between adjacent chunks
MIN_CHUNK_SIZE = 128       # don't create tiny chunks
MAX_DRAWER_CONTENT = 4096  # max chars storable in a drawer entry
CLOSET_CHAR_LIMIT = 300    # max chars in a closet line (compact pointer)
CLOSET_EXTRACT_WINDOW = 3  # lines before/after matched line for context


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class DrawerEntry:
    """A raw verbatim chunk (drawer) from canonical memory content.

    Drawers are the evidence layer: full text, immutable, source-linked.
    """
    drawer_id: str
    memory_id: str
    content: str
    chunk_index: int = 0
    offset_start: int = 0
    offset_end: int = 0
    content_hash: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.content_hash and self.content:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()

    def truncated(self, max_chars: int = MAX_DRAWER_CONTENT) -> str:
        return self.content[:max_chars] + ("..." if len(self.content) > max_chars else "")


@dataclass
class ClosetEntry:
    """A compact semantic pointer from a memory to its drawer(s).

    Closets are the retrieval layer: compact, searchable, pointer-only.
    Each closet entry describes one semantic chunk + where to find the evidence.
    """
    closet_id: str
    memory_id: str
    drawer_id: str
    line_start: int = 0
    line_end: int = 0
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    chunk_index: int = 0
    memory_type: str = "context"
    score: float = 0.5
    created_at: str = ""

    def pointer(self) -> str:
        """Compact pointer string: drawer_id:L{line_start}-L{line_end}"""
        return f"{self.drawer_id}:L{self.line_start}-L{self.line_end}"


# ── Drawer Builder ───────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict[str, Any]]:
    """Split text into overlapping chunks with offset tracking."""
    if not text:
        return []
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk_text = text[start:end]
        if len(chunk_text) >= MIN_CHUNK_SIZE or idx == 0:
            chunks.append({
                "content": chunk_text,
                "offset_start": start,
                "offset_end": end,
                "chunk_index": idx,
            })
        idx += 1
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def _extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    """Extract significant keywords from text."""
    words = re.findall(r'\b[A-Z][A-Za-z0-9_.\-/]{2,}\b', text)  # capitalized entities
    words += re.findall(r'\b[a-z]{4,}\b', text.lower())  # common words
    # Remove stopwords
    stop = {"this", "that", "with", "from", "have", "been", "were", "what", "which", "their", "they", "them", "some", "into", "also", "than", "then", "about", "would", "could", "should", "after", "other", "there", "these", "those", "while", "where", "when", "very", "just", "more", "such"}
    seen = set()
    out = []
    for w in words:
        w = w.strip().lower()
        if len(w) >= 3 and w not in stop and w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= max_keywords:
            break
    return out


# ── Build Closets for One Memory ─────────────────────────────────────────────

def _build_closet_lines(memory_id: str, content: str, memory_type: str = "context") -> tuple[list[DrawerEntry], list[ClosetEntry]]:
    """Build draw entries + closet entries for a single memory.

    Returns (drawer_entries, closet_entries).
    """
    chunks = _chunk_text(content)
    drawers: list[DrawerEntry] = []
    closets: list[ClosetEntry] = []

    for chunk in chunks:
        chunk_text = chunk["content"]
        drawer_id = hashlib.sha256(f"{memory_id}::{chunk['chunk_index']}::{chunk_text[:64]}".encode()).hexdigest()[:16]

        # Estimate line range (conservative ~80 chars/line)
        line_start = chunk["offset_start"] // 80 + 1
        line_end = chunk["offset_end"] // 80 + 1

        # Summary: first 300 chars
        summary = chunk_text[:CLOSET_CHAR_LIMIT]
        if len(chunk_text) > CLOSET_CHAR_LIMIT:
            summary += "..."

        keywords = _extract_keywords(chunk_text)

        now = datetime.now(timezone.utc).isoformat()

        drawers.append(DrawerEntry(
            drawer_id=drawer_id,
            memory_id=memory_id,
            content=chunk_text,
            chunk_index=chunk["chunk_index"],
            offset_start=chunk["offset_start"],
            offset_end=chunk["offset_end"],
            created_at=now,
        ))

        closets.append(ClosetEntry(
            closet_id=f"closet:{drawer_id}",
            memory_id=memory_id,
            drawer_id=drawer_id,
            line_start=line_start,
            line_end=line_end,
            summary=summary,
            keywords=keywords,
            chunk_index=chunk["chunk_index"],
            memory_type=memory_type,
            created_at=now,
        ))

    return drawers, closets


# ── SQLite Persistence ───────────────────────────────────────────────────────

def _ensure_tables(store: SuperMemoryStore) -> None:
    with store.connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS palace_drawers (
                drawer_id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                content TEXT NOT NULL,
                chunk_index INTEGER NOT NULL DEFAULT 0,
                offset_start INTEGER NOT NULL DEFAULT 0,
                offset_end INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        # Backward-compatible migration for pre-v1 drawer tables.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(palace_drawers)").fetchall()}
        required = {"drawer_id", "memory_id", "content", "chunk_index", "offset_start", "offset_end", "content_hash", "created_at"}
        if "drawer_id" not in cols:
            # Old derived projection schemas are safe to rebuild from canonical memories.
            conn.executescript("DROP TABLE IF EXISTS palace_closets; DROP TABLE IF EXISTS palace_drawers;")
            conn.executescript("""
            CREATE TABLE palace_drawers (
                drawer_id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                content TEXT NOT NULL,
                chunk_index INTEGER NOT NULL DEFAULT 0,
                offset_start INTEGER NOT NULL DEFAULT 0,
                offset_end INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """)
            cols = required
        if "content_hash" not in cols:
            conn.execute("ALTER TABLE palace_drawers ADD COLUMN content_hash TEXT")
        # Coexist with older MemPalace spatial schema users that expect wing/room/hall/id.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(palace_drawers)").fetchall()}
        compat_cols = {
            "id": "TEXT",
            "wing": "TEXT NOT NULL DEFAULT 'semantic'",
            "room": "TEXT NOT NULL DEFAULT 'closets'",
            "hall": "TEXT NOT NULL DEFAULT 'drawers'",
            "checksum": "TEXT",
            "source": "TEXT",
            "source_file": "TEXT",
            "metadata_json": "TEXT DEFAULT '{}'",
        }
        for col, spec in compat_cols.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE palace_drawers ADD COLUMN {col} {spec}")  # nosec-sql: col/spec come from the fixed compat_cols dict literal
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_drawers_memory_id ON palace_drawers(memory_id);
            CREATE INDEX IF NOT EXISTS idx_drawers_content_hash ON palace_drawers(content_hash);

            CREATE TABLE IF NOT EXISTS palace_closets (
                closet_id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                drawer_id TEXT NOT NULL,
                line_start INTEGER NOT NULL DEFAULT 0,
                line_end INTEGER NOT NULL DEFAULT 0,
                summary TEXT NOT NULL DEFAULT '',
                keywords TEXT NOT NULL DEFAULT '[]',
                chunk_index INTEGER NOT NULL DEFAULT 0,
                memory_type TEXT NOT NULL DEFAULT 'context',
                score REAL NOT NULL DEFAULT 0.5,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_closets_memory_id ON palace_closets(memory_id);
            CREATE INDEX IF NOT EXISTS idx_closets_drawer_id ON palace_closets(drawer_id);
            CREATE INDEX IF NOT EXISTS idx_closets_keywords ON palace_closets(keywords);
        """)


# ── Public API ───────────────────────────────────────────────────────────────

def build_closets(memory_id: str, content: str, memory_type: str = "context", config_path: str | None = None) -> dict[str, Any]:
    """Build and persist drawer + closet entries for one memory."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    drawers, closets = _build_closet_lines(memory_id, content, memory_type=memory_type)

    with store.connect() as conn:
        # Upsert drawers
        for d in drawers:
            d_dict = asdict(d)
            cols = ", ".join(d_dict.keys())
            placeholders = ", ".join(["?"] * len(d_dict))
            vals = list(d_dict.values())
            conn.execute(
                f"INSERT OR REPLACE INTO palace_drawers ({cols}) VALUES ({placeholders})",
                vals,
            )
        # Upsert closets
        for c in closets:
            c_dict = asdict(c)
            c_dict["keywords"] = json.dumps(c_dict["keywords"])
            cols = ", ".join(c_dict.keys())
            placeholders = ", ".join(["?"] * len(c_dict))
            vals = list(c_dict.values())
            conn.execute(
                f"INSERT OR REPLACE INTO palace_closets ({cols}) VALUES ({placeholders})",
                vals,
            )
        # Mark long canonical memories as mitigated once their verbatim drawers and
        # semantic closets are present. Canonical content is retained for provenance.
        if len(content) > 2000:
            try:
                row = conn.execute("SELECT metadata_json FROM memories WHERE id=? AND layer='workspace_markdown'", (memory_id,)).fetchone()
                meta = json.loads(row["metadata_json"] or "{}") if row else {}
                meta["compression_policy"] = "verbatim_drawers_plus_summary"
                meta["canonical_retained"] = True
                meta["closet_status"] = "built"
                meta["drawer_count"] = len(drawers)
                meta["closet_count"] = len(closets)
                conn.execute("UPDATE memories SET metadata_json=? WHERE id=? AND layer='workspace_markdown'", (json.dumps(meta, ensure_ascii=False), memory_id))
                conn.commit()
            except Exception:
                pass
        conn.commit()

    return {
        "ok": True,
        "memory_id": memory_id,
        "drawers_created": len(drawers),
        "closets_created": len(closets),
    }


def rebuild_closets(limit: int = 500, config_path: str | None = None) -> dict[str, Any]:
    """Rebuild closets for active workspace_markdown memories."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM memories WHERE layer='workspace_markdown' AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    total_drawers = 0
    total_closets = 0
    errors = []

    for row in rows:
        rec = row_to_memory(row)
        try:
            result = build_closets(rec.id, rec.content, rec.type.value, config_path=config_path)
            total_drawers += result["drawers_created"]
            total_closets += result["closets_created"]
        except Exception as e:
            errors.append({"memory_id": rec.id, "error": str(e)})

    # Purge stale closets (orphaned memory_ids)
    with store.connect() as conn:
        conn.execute("""
            DELETE FROM palace_closets WHERE memory_id NOT IN (
                SELECT id FROM memories WHERE layer='workspace_markdown' AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0
            )
        """)
        conn.execute("""
            DELETE FROM palace_drawers WHERE memory_id NOT IN (
                SELECT id FROM memories WHERE layer='workspace_markdown' AND COALESCE(json_extract(metadata_json,'$.soft_deleted'),0)=0
            )
        """)
        conn.commit()

    return {
        "ok": len(errors) == 0,
        "memories_processed": len(rows),
        "total_drawers": total_drawers,
        "total_closets": total_closets,
        "errors": errors,
    }


def search_closets(query: str, limit: int = 10, config_path: str | None = None) -> dict[str, Any]:
    """Search closets by keyword match and return best matching closets.

    Returns closet entries with hydrated content summaries.
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    # Tokenize query into keywords
    query_keywords = set(re.findall(r'\w{3,}', query.lower()))
    if not query_keywords:
        return {"ok": True, "query": query, "results": [], "count": 0}

    with store.connect() as conn:
        # Search closets by keyword overlap
        all_closets = conn.execute(
            "SELECT * FROM palace_closets ORDER BY score DESC LIMIT ?",
            (limit * 5,),
        ).fetchall()

    scored = []
    for row in all_closets:
        try:
            keywords = json.loads(row["keywords"]) if isinstance(row["keywords"], str) else (row["keywords"] or [])
        except (json.JSONDecodeError, TypeError):
            keywords = []
        kw_lower = set(k.lower() for k in (keywords or []))
        overlap = len(query_keywords & kw_lower)
        if overlap == 0:
            continue
        # Also check summary
        summary_lower = (row["summary"] or "").lower()
        summary_overlap = len(query_keywords & set(re.findall(r'\w{3,}', summary_lower)))
        score = (overlap * 0.6 + summary_overlap * 0.4) / max(len(query_keywords), 1)
        if score > 0:
            scored.append({
                "closet_id": row["closet_id"],
                "memory_id": row["memory_id"],
                "drawer_id": row["drawer_id"],
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "summary": row["summary"],
                "keywords": keywords,
                "score": round(score, 4),
                "pointer": f"{row['drawer_id']}:L{row['line_start']}-L{row['line_end']}",
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"ok": True, "query": query, "results": scored[:limit], "count": len(scored[:limit])}


def hydrate_closets(closet_ids: list[str] | None = None, drawer_ids: list[str] | None = None, line_context: int = CLOSET_EXTRACT_WINDOW, config_path: str | None = None) -> dict[str, Any]:
    """Hydrate full content from closet/drawer references.

    Returns the raw verbatim drawer content with neighbor expansion.
    """
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    results = []

    with store.connect() as conn:
        if drawer_ids:
            placeholders = ", ".join(["?"] * len(drawer_ids))
            rows = conn.execute(
                f"SELECT * FROM palace_drawers WHERE drawer_id IN ({placeholders})",
                drawer_ids,
            ).fetchall()
        elif closet_ids:
            placeholders = ", ".join(["?"] * len(closet_ids))
            rows = conn.execute(
                f"SELECT d.* FROM palace_drawers d JOIN palace_closets c ON d.drawer_id = c.drawer_id WHERE c.closet_id IN ({placeholders})",
                closet_ids,
            ).fetchall()
        else:
            return {"ok": False, "error": "provide closet_ids or drawer_ids", "results": []}

        for row in rows:
            # Neighbor expansion: ±CLOSET_EXTRACT_WINDOW chunks
            neighbor_rows = conn.execute(
                "SELECT * FROM palace_drawers WHERE memory_id=? AND chunk_index BETWEEN ? AND ? ORDER BY chunk_index",
                (row["memory_id"], max(0, row["chunk_index"] - line_context), row["chunk_index"] + line_context),
            ).fetchall()

            full_content = " ".join(nr["content"] for nr in neighbor_rows)
            results.append({
                "drawer_id": row["drawer_id"],
                "memory_id": row["memory_id"],
                "chunk_index": row["chunk_index"],
                "offset_start": row["offset_start"],
                "offset_end": row["offset_end"],
                "content": full_content[:MAX_DRAWER_CONTENT],
                "content_hash": row["content_hash"],
                "neighbor_chunks": len(neighbor_rows),
            })

    return {"ok": True, "hydrated": len(results), "results": results}


def closet_stats(config_path: str | None = None) -> dict[str, Any]:
    """Get closet/drawer statistics."""
    cfg = load_config(config_path)
    store = SuperMemoryStore(cfg)
    _ensure_tables(store)

    with store.connect() as conn:
        try:
            drawer_count = conn.execute("SELECT COUNT(*) as c FROM palace_drawers").fetchone()["c"]
        except Exception:
            drawer_count = 0
        try:
            closet_count = conn.execute("SELECT COUNT(*) as c FROM palace_closets").fetchone()["c"]
        except Exception:
            closet_count = 0
        try:
            memory_count = conn.execute("SELECT COUNT(DISTINCT memory_id) as c FROM palace_closets").fetchone()["c"]
        except Exception:
            memory_count = 0

    return {
        "ok": True,
        "drawer_count": drawer_count,
        "closet_count": closet_count,
        "memories_indexed": memory_count,
    }
