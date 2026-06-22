"""OpenClaw compatibility shim for Super Memory.

P2 #6: CJK trigram FTS5 support — auto-detect CJK queries and route to
trigram-indexed FTS5 tables for multi-language search.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_config
from .models import MemoryLayer, MemoryRecord, SuperMemoryConfig
from .service import SuperMemoryService
from .storage import SuperMemoryStore


@dataclass
class MemorySearchHit:
    id: str
    path: str
    startLine: int
    endLine: int
    score: float
    textScore: float
    snippet: str
    source: str
    corpus: str
    layer: str
    memory_id: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


# ── CJK detection ─────────────────────────────────────────────────


def _has_cjk(text: str) -> bool:
    """Check if text contains CJK characters (Chinese, Japanese, Korean)."""
    for ch in text:
        cp = ord(ch)
        # CJK Unified Ideographs
        if 0x4E00 <= cp <= 0x9FFF:
            return True
        # Hangul Syllables
        if 0xAC00 <= cp <= 0xD7AF:
            return True
        # Katakana
        if 0x30A0 <= cp <= 0x30FF:
            return True
        # Hiragana
        if 0x3040 <= cp <= 0x309F:
            return True
        # CJK Extension A
        if 0x3400 <= cp <= 0x4DBF:
            return True
        # CJK Compatibility Ideographs
        if 0xF900 <= cp <= 0xFAFF:
            return True
    return False


def _cjk_fts_search(store: SuperMemoryStore, query: str, limit: int = 10) -> list[MemoryRecord]:
    """Search CJK trigram FTS5 tables when query contains CJK characters.

    Falls back silently if trigram tables don't exist or query causes errors.
    Converts multi-word CJK queries into FTS5-safe OR terms.
    """
    from .storage import row_to_memory

    results: list[MemoryRecord] = []
    # FTS5 trigram doesn't support OR/AND — use individual terms
    terms = [t.strip() for t in query.split() if len(t.strip()) >= 1]
    with store.connect() as conn:
        for table in ("memories_cjk_fts",):
            try:
                for term in terms[:3]:  # Limit to 3 terms
                    rows = conn.execute(
                        f"SELECT m.* FROM {table} f JOIN memories m ON m.rowid = f.rowid WHERE {table} MATCH ? ORDER BY rank LIMIT ?",
                        (term, max(limit // len(terms), 1)),
                    ).fetchall()
                    for row in rows:
                        mem = row_to_memory(row)
                        if not any(r.id == mem.id for r in results):
                            results.append(mem)
            except Exception:
                continue
    return results[:limit]


# ── Main search ───────────────────────────────────────────────────


def memory_search_compatible(
    query: str,
    *,
    max_results: int = 5,
    min_score: float = 0.0,
    corpus: str = "all",
    config: SuperMemoryConfig | None = None,
) -> dict[str, Any]:
    """Return a memory_search-like payload for OpenClaw compatibility.

    Auto-detects CJK queries and routes to trigram FTS5 tables for
    multi-language search support.
    """

    cfg = config or load_config(None)
    svc = SuperMemoryService(cfg)
    hits: list[MemorySearchHit] = []

    # CJK path: use trigram FTS5 tables directly
    if _has_cjk(query):
        store = SuperMemoryStore(cfg)
        cjk_records = _cjk_fts_search(store, query, limit=max_results)
        for idx, record in enumerate(cjk_records):
            score = _score_record(query, record, base=1.0 - (idx * 0.05))
            if score < min_score:
                continue
            hit = _record_to_hit(record, layer=MemoryLayer.PROJECTION, score=score, query=query)
            hits.append(hit)
        hits.sort(key=lambda h: h.score, reverse=True)
        hits = hits[:max_results]
        return {
            "results": [h.to_dict() for h in hits],
            "provider": "super-memory",
            "citations": "auto",
            "debug": {
                "backend": "super-memory",
                "corpus": corpus,
                "hits": len(hits),
                "cjk": True,
            },
        }

    # Standard path: use existing layer recall
    layer_hits = svc.recall(query, limit=max_results)
    for layer, records in layer_hits.items():
        if corpus != "all" and not _layer_in_corpus(layer, corpus):
            continue
        for idx, record in enumerate(records):
            score = _score_record(query, record, base=1.0 - (idx * 0.05))
            if score < min_score:
                continue
            hit = _record_to_hit(record, layer=layer, score=score, query=query)
            hits.append(hit)
    hits.sort(key=lambda h: h.score, reverse=True)
    hits = hits[:max_results]
    return {
        "results": [h.to_dict() for h in hits],
        "provider": "super-memory",
        "citations": "auto",
        "debug": {
            "backend": "super-memory",
            "corpus": corpus,
            "hits": len(hits),
            "cjk": False,
        },
    }


def memory_get_compatible(
    path: str,
    *,
    from_line: int = 1,
    lines: int = 20,
    corpus: str = "all",
    config: SuperMemoryConfig | None = None,
) -> dict[str, Any]:
    cfg = config or load_config(None)
    if path.startswith("super-memory://"):
        return _memory_get_virtual(path, cfg)
    return _memory_get_file(path, cfg, from_line=from_line, lines=lines)


def _record_to_hit(record: MemoryRecord, *, layer: MemoryLayer, score: float, query: str) -> MemorySearchHit:
    source_path = record.source or f"super-memory://{layer.value}/{record.id}"
    snippet = _snippet(record.content, query)
    return MemorySearchHit(
        id=f"{layer.value}:{record.id}",
        path=source_path,
        startLine=1,
        endLine=max(1, len(record.content.splitlines())),
        score=score,
        textScore=score,
        snippet=snippet,
        source="super-memory",
        corpus=_corpus_for_layer(layer),
        layer=layer.value,
        memory_id=record.id,
    )


def _memory_get_virtual(path: str, cfg: SuperMemoryConfig) -> dict[str, Any]:
    try:
        _, rest = path.split("super-memory://", 1)
        layer, memory_id = rest.split("/", 1)
    except ValueError:
        return {"path": path, "error": "invalid super-memory virtual path"}
    store = SuperMemoryStore(cfg)
    record = store.get_memory(memory_id, layer=layer)
    if not record:
        return {"path": path, "error": "memory not found"}
    text = record.content
    return {
        "path": path,
        "from": 1,
        "lines": len(text.splitlines()) or 1,
        "content": text,
        "truncated": False,
        "source": "super-memory",
        "metadata": record.model_dump(mode="json"),
    }


def _memory_get_file(path: str, cfg: SuperMemoryConfig, *, from_line: int, lines: int) -> dict[str, Any]:
    root = Path(cfg.workspace_root)
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = root / file_path
    try:
        resolved = file_path.resolve()
        resolved.relative_to(root.resolve())
    except Exception:
        return {"path": path, "error": "path outside workspace"}
    if not file_path.exists():
        return {"path": path, "error": "file not found"}
    all_lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = max(1, from_line)
    end = min(len(all_lines), start + max(1, lines) - 1)
    content = "\n".join(all_lines[start - 1 : end])
    return {
        "path": str(file_path),
        "from": start,
        "lines": end - start + 1 if all_lines else 0,
        "content": content,
        "truncated": end < len(all_lines),
        "source": "workspace",
    }


def _score_record(query: str, record: MemoryRecord, *, base: float) -> float:
    q = query.lower()
    c = record.content.lower()
    if q in c:
        return max(base, 0.95)
    terms = [t for t in q.split() if t]
    if not terms:
        return base
    matched = sum(1 for term in terms if term in c)
    return max(0.0, min(1.0, base * (matched / len(terms))))


def _snippet(content: str, query: str, max_chars: int = 500) -> str:
    if len(content) <= max_chars:
        return content
    idx = content.lower().find(query.lower())
    if idx < 0:
        return content[:max_chars] + "…"
    start = max(0, idx - max_chars // 3)
    end = min(len(content), start + max_chars)
    return ("…" if start else "") + content[start:end] + ("…" if end < len(content) else "")


def _corpus_for_layer(layer: MemoryLayer) -> str:
    if layer == MemoryLayer.WORKSPACE_MARKDOWN:
        return "memory"
    return "super-memory"


def _layer_in_corpus(layer: MemoryLayer, corpus: str) -> bool:
    if corpus == "memory":
        return layer == MemoryLayer.WORKSPACE_MARKDOWN
    if corpus == "super-memory":
        return layer != MemoryLayer.WORKSPACE_MARKDOWN
    return True
