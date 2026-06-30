"""OpenClaw compatibility shim for Super Memory.

Produces standard memory_search / memory_get output matching OpenClaw memory-core:
- memory_search: { results: [{id, path, startLine, endLine, score, textScore, snippet, source, corpus, citation}], provider, citations }
- memory_get:   { path, from, lines, content, truncated, source, metadata }
- corpus:       "memory" | "sessions" | "super-memory" | "all"
- CJK trigram FTS5 auto-detection
- Session transcript FTS5 search via session_index module
- Cooldown + timeout integration
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .storage import sqlite_path

from .config import load_config
from .models import MemoryLayer, MemoryRecord, SuperMemoryConfig
from .service import SuperMemoryService
from .storage import SuperMemoryStore
from .cooldown import get_cooldown_manager, Deadline, TimeoutError


# ── Standard Search Hit ─────────────────────────────────────────────────────


@dataclass
class MemorySearchHit:
    """Standard memory_search result matching OpenClaw memory-core format."""

    id: str = ""
    path: str = ""
    startLine: int = 1
    endLine: int = 1
    score: float = 0.0
    textScore: float = 0.0
    vectorScore: float | None = None
    snippet: str = ""
    source: str = "super-memory"
    corpus: str = "memory"
    citation: str = ""
    # Super Memory extensions
    layer: str = ""
    memory_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "path": self.path,
            "startLine": self.startLine,
            "endLine": self.endLine,
            "score": self.score,
            "textScore": self.textScore,
            "snippet": self.snippet,
            "source": self.source,
            "corpus": self.corpus,
            "citation": self.citation,
        }
        if self.vectorScore is not None:
            d["vectorScore"] = self.vectorScore
        return d


# ── CJK detection ─────────────────────────────────────────────────


CJK_RANGES = [
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0xAC00, 0xD7AF),   # Hangul Syllables
    (0x30A0, 0x30FF),   # Katakana
    (0x3040, 0x309F),   # Hiragana
    (0x3400, 0x4DBF),   # CJK Extension A
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
]


def _has_cjk(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        for lo, hi in CJK_RANGES:
            if lo <= cp <= hi:
                return True
    return False


def _cjk_fts_search(store: SuperMemoryStore, query: str, limit: int = 10) -> list[MemoryRecord]:
    """Search CJK trigram FTS5 tables."""
    from .storage import row_to_memory

    results: list[MemoryRecord] = []
    terms = [t.strip() for t in query.split() if len(t.strip()) >= 1]
    with store.connect() as conn:
        for term in terms[:3]:
            try:
                rows = conn.execute(
                    "SELECT m.* FROM memories_cjk_fts f JOIN memories m ON m.rowid = f.rowid WHERE memories_cjk_fts MATCH ? ORDER BY rank LIMIT ?",
                    (term, max(limit // len(terms), 1)),
                ).fetchall()
                for row in rows:
                    mem = row_to_memory(row)
                    if not any(r.id == mem.id for r in results):
                        results.append(mem)
            except Exception:
                continue
    return results[:limit]


# ── Layer helpers ───────────────────────────────────────────────────────────


def _corpus_for_layer(layer: MemoryLayer) -> str:
    if layer == MemoryLayer.WORKSPACE_MARKDOWN:
        return "memory"
    return "super-memory"


def _layer_in_corpus(layer: MemoryLayer, corpus: str) -> bool:
    if corpus == "memory":
        return layer == MemoryLayer.WORKSPACE_MARKDOWN
    if corpus == "super-memory":
        return layer != MemoryLayer.WORKSPACE_MARKDOWN
    if corpus == "sessions":
        return False  # Sessions is separate
    return True  # "all"


# ── Scoring ─────────────────────────────────────────────────────────────────


def _score_record(query: str, record: MemoryRecord, *, base: float) -> float:
    q = query.lower()
    c = _ranking_content(record).lower()
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


def _ranking_content(record: MemoryRecord) -> str:
    """Return compact text for scoring/snippets without losing provenance.

    Long-memory mitigation keeps canonical verbatim content in workspace_markdown
    and stores a compact summary in metadata. Search ranking/snippets should use
    that summary so raw transcripts do not dominate recall by sheer length; callers
    can still hydrate/show the canonical record for evidence.
    """
    meta = record.metadata or {}
    summary = meta.get("summary")
    if (
        meta.get("compression_policy") == "verbatim_drawers_plus_summary"
        and meta.get("canonical_retained") in (True, 1, "true", "True")
        and isinstance(summary, str)
        and summary.strip()
    ):
        return summary.strip()
    return record.content


# ── Main search ─────────────────────────────────────────────────────────────


def memory_search_compatible(
    query: str,
    *,
    max_results: int = 5,
    min_score: float = 0.0,
    corpus: str = "all",
    config: SuperMemoryConfig | None = None,
    cooldown_key: str | None = None,
) -> dict[str, Any]:
    """Return a standard memory_search payload matching OpenClaw memory-core.

    Supports corpora:
    - "memory": workspace_markdown layer only (.md files)
    - "sessions": session transcript FTS5 index
    - "super-memory": mempalace + honcho + neural_memory layers
    - "all": all of the above merged

    Auto-detects CJK queries and routes to trigram FTS5.
    """
    cfg = config or load_config(None)
    cd_key = cooldown_key or f"search:{corpus}:{_hash_query(query)}"

    # Fast path for fresh/local test configs: avoid booting the full layered
    # service and migration stack when there is obviously nothing to search.
    db_path = sqlite_path(cfg)
    memory_dir = Path(cfg.workspace_root) / cfg.daily_memory_dir
    if corpus in ("all", "memory", "super-memory") and not db_path.exists() and not memory_dir.exists():
        return {
            "results": [],
            "provider": "super-memory",
            "citations": "auto",
            "debug": {"backend": "super-memory", "corpus": corpus, "hits": 0, "fast_path": "empty_workspace"},
        }

    # Check cooldown
    cd_mgr = get_cooldown_manager()
    cached_error = cd_mgr.check(cd_key)
    if cached_error:
        return _unavailable_result(cached_error, corpus)

    # Start deadline
    deadline = Deadline()

    try:
        results, debug_info = _run_search(query, max_results, min_score, corpus, cfg, deadline)
        cd_mgr.record_success(cd_key)
        return {
            "results": results,
            "provider": "super-memory",
            "citations": "auto",
            "debug": {
                "backend": "super-memory",
                "corpus": corpus,
                "hits": len(results),
                "timed_out": deadline.timed_out,
                **debug_info,
            },
        }
    except TimeoutError:
        cd_mgr.record_success(cd_key)  # timeout is transient, don't cooldown
        return _unavailable_result(f"search timed out after {Deadline.DEFAULT_TIMEOUT_MS}ms", corpus)
    except Exception as exc:
        err_str = f"{type(exc).__name__}: {exc}"
        cd_mgr.record_error(cd_key, err_str)
        return _unavailable_result(err_str, corpus)


def _hash_query(query: str) -> str:
    """Simple query hash for cooldown key."""
    return str(hash(query) & 0xFFFFFFFF)


def _unavailable_result(error: str, corpus: str = "all") -> dict[str, Any]:
    return {
        "results": [],
        "provider": "super-memory",
        "citations": "auto",
        "unavailable": True,
        "disabled": True,
        "error": error,
        "debug": {"backend": "super-memory", "corpus": corpus, "hits": 0},
    }


# ── Search execution ────────────────────────────────────────────────────────


def _run_search(
    query: str,
    max_results: int,
    min_score: float,
    corpus: str,
    cfg: SuperMemoryConfig,
    deadline: Deadline,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Execute search across requested corpora."""
    deadline.check()
    hits: list[MemorySearchHit] = []
    debug: dict[str, Any] = {}

    include_memory = corpus in ("all", "memory")
    include_sessions = corpus in ("all", "sessions")
    include_sm = corpus in ("all", "super-memory")
    cjk = _has_cjk(query)

    if cjk:
        debug["cjk"] = True
        hits = _cjk_search(query, max_results, min_score, cfg, deadline)
    else:
        if include_memory:
            deadline.check()
            memory_hits = _search_layer(query, max_results, min_score, cfg, MemoryLayer.WORKSPACE_MARKDOWN, "memory")
            hits.extend(memory_hits)

        if include_sm:
            deadline.check()
            for layer in (MemoryLayer.MEMPALACE, MemoryLayer.HONCHO, MemoryLayer.NEURAL_MEMORY):
                layer_hits = _search_layer(query, max_results // 2, min_score, cfg, layer, "super-memory")
                hits.extend(layer_hits)

    # Merge + sort + dedup
    seen_paths: set[str] = set()
    deduped: list[MemorySearchHit] = []
    for h in sorted(hits, key=lambda x: x.score, reverse=True):
        key = h.path or h.id
        if key not in seen_paths:
            seen_paths.add(key)
            deduped.append(h)

    deduped = deduped[:max_results]

    # Include sessions (separate FTS index)
    if include_sessions and not cjk:
        deadline.check()
        try:
            from .session_index import search_sessions as _ss

            sres = _ss(query, max_results=max_results, min_score=min_score, config_path=getattr(cfg, 'config_path', None))
            for sr in sres.get("results", []):
                sr_key = sr.get("path", sr.get("id", ""))
                if sr_key not in seen_paths and sr.get("score", 0) >= min_score:
                    deduped.append(sr)
                    seen_paths.add(sr_key)
        except Exception:
            debug["sessions_error"] = "session index unavailable"

    deduped = sorted(deduped, key=lambda x: x.get("score", 0) if isinstance(x, dict) else x.score, reverse=True)[:max_results]

    # Convert to dicts
    final = []
    for h in deduped:
        if isinstance(h, MemorySearchHit):
            final.append(h.to_dict())
        else:
            final.append(h)

    return final, debug


def _cjk_search(
    query: str, max_results: int, min_score: float,
    cfg: SuperMemoryConfig, deadline: Deadline,
) -> list[MemorySearchHit]:
    """CJK-specific search via trigram FTS5."""
    deadline.check()
    store = SuperMemoryStore(cfg)
    cjk_records = _cjk_fts_search(store, query, limit=max_results)
    hits: list[MemorySearchHit] = []
    for idx, record in enumerate(cjk_records):
        deadline.check()
        score = _score_record(query, record, base=1.0 - (idx * 0.05))
        if score < min_score:
            continue
        hit = _record_to_hit(record, layer=MemoryLayer.NEURAL_MEMORY, score=score, query=query)
        hits.append(hit)
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:max_results]


def _search_layer(
    query: str, max_results: int, min_score: float,
    cfg: SuperMemoryConfig, layer: MemoryLayer, corpus_name: str,
) -> list[MemorySearchHit]:
    """Search one memory layer."""
    svc = SuperMemoryService(cfg)
    try:
        records = svc.search_layer(layer, query, limit=max_results)
    except AttributeError:
        # Fallback: use recall
        layer_hits = svc.recall(query, limit=max_results)
        records = layer_hits.get(layer, [])

    hits: list[MemorySearchHit] = []
    for idx, record in enumerate(records):
        score = _score_record(query, record, base=1.0 - (idx * 0.05))
        if score < min_score:
            continue
        hit = _record_to_hit(record, layer=layer, score=score, query=query)
        hit.corpus = corpus_name
        hits.append(hit)
    return hits


# ── Record → Hit conversion ────────────────────────────────────────────────


def _record_to_hit(record: MemoryRecord, *, layer: MemoryLayer, score: float, query: str) -> MemorySearchHit:
    source_path = record.source or f"super-memory://{layer.value}/{record.id}"
    display_content = _ranking_content(record)
    snippet = _snippet(display_content, query)
    return MemorySearchHit(
        id=f"{layer.value}:{record.id}",
        path=source_path,
        startLine=1,
        endLine=max(1, len(display_content.splitlines())),
        score=score,
        textScore=score,
        snippet=snippet,
        source="super-memory",
        corpus=_corpus_for_layer(layer),
        citation=_make_citation(record),
        layer=layer.value,
        memory_id=record.id,
    )


def _make_citation(record: MemoryRecord) -> str:
    parts = []
    if record.project:
        parts.append(record.project)
    if record.session_id:
        parts.append(f"session:{record.session_id[:16]}")
    return " · ".join(parts)


# ── memory_get ──────────────────────────────────────────────────────────────


def memory_get_compatible(
    path: str,
    *,
    from_line: int = 1,
    lines: int = 20,
    corpus: str = "all",
    config: SuperMemoryConfig | None = None,
) -> dict[str, Any]:
    """Standard memory_get output matching OpenClaw memory-core format.

    Returns: { path, from, lines, content, truncated, source, metadata }
    """
    cfg = config or load_config(None)
    if path.startswith("super-memory://"):
        return _memory_get_virtual(path, cfg)
    return _memory_get_file(path, cfg, from_line=from_line, lines=lines)


def _memory_get_virtual(path: str, cfg: SuperMemoryConfig) -> dict[str, Any]:
    try:
        _, rest = path.split("super-memory://", 1)
        layer, memory_id = rest.split("/", 1)
    except ValueError:
        return {"path": path, "error": "invalid super-memory virtual path", "source": "super-memory"}
    store = SuperMemoryStore(cfg)
    record = store.get_memory(memory_id, layer=layer)
    if not record:
        return {"path": path, "error": "memory not found", "source": "super-memory"}
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


# ── Micro-gap 7: CJK Tokenize Utility ─────────────────────────────────

# Mirrors memory-core tokenize.ts:
#   tokenize(text) -> Set[str]
#   jaccardSimilarity(setA, setB) -> float
#   textSimilarity(contentA, contentB) -> float

# Unicode ranges matching memory-core CJK_RE:
# Hiragana (3040-309F), Katakana (30A0-30FF),
# CJK Ext A (3400-4DBF), CJK Unified (4E00-9FFF),
# Hangul Syllables (AC00-D7AF), Hangul Jamo (1100-11FF)
_CJK_RE = re.compile(
    r'[\u3040-\u309f\u30a0-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\u1100-\u11ff]'
)


def tokenize(text: str) -> set[str]:
    """Tokenize text for Jaccard similarity computation.

    Mirrors memory-core `tokenize()`:
    - Extracts alphanumeric tokens (a-z, 0-9, _)
    - Extracts CJK-family unigrams (single characters)
    - Extracts CJK bigrams from originally adjacent characters

    Args:
        text: Input text to tokenize.

    Returns:
        Set of tokens (lowercase).
    """
    lower = text.lower()
    ascii_tokens = re.findall(r'[a-z0-9_]+', lower)

    # Extract CJK characters with their original positions
    chars = list(lower)
    cjk_data: list[tuple[str, int]] = []
    for i, ch in enumerate(chars):
        if _CJK_RE.match(ch):
            cjk_data.append((ch, i))

    # Build bigrams only from originally adjacent CJK characters
    bigrams: list[str] = []
    for i in range(len(cjk_data) - 1):
        if cjk_data[i + 1][1] == cjk_data[i][1] + 1:
            bigrams.append(cjk_data[i][0] + cjk_data[i + 1][0])

    unigrams = [d[0] for d in cjk_data]
    return set(ascii_tokens + bigrams + unigrams)


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two token sets.

    Mirrors memory-core `jaccardSimilarity()`.
    Returns value in [0, 1] where 1 means identical sets.

    Args:
        set_a: First token set.
        set_b: Second token set.

    Returns:
        Jaccard similarity score.
    """
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0

    # Iterate over smaller set for efficiency
    smaller = set_a if len(set_a) <= len(set_b) else set_b
    larger = set_b if len(set_a) <= len(set_b) else set_a

    intersection_size = sum(1 for token in smaller if token in larger)
    union_size = len(set_a) + len(set_b) - intersection_size
    return 0.0 if union_size == 0 else intersection_size / union_size


def text_similarity(content_a: str, content_b: str) -> float:
    """Compute text similarity using Jaccard on tokens.

    Mirrors memory-core `textSimilarity()`.
    Falls back to exact string equality when both token sets are empty.

    Args:
        content_a: First content string.
        content_b: Second content string.

    Returns:
        Similarity score in [0, 1].
    """
    tokens_a = tokenize(content_a)
    tokens_b = tokenize(content_b)
    if not tokens_a and not tokens_b:
        # Fallback to exact normalized equality (same as memory-core)
        return 1.0 if content_a.lower() == content_b.lower() else 0.0
    return jaccard_similarity(tokens_a, tokens_b)


def _memory_get_file(path: str, cfg: SuperMemoryConfig, *, from_line: int, lines: int) -> dict[str, Any]:
    root = Path(cfg.workspace_root)
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = root / file_path
    try:
        resolved = file_path.resolve()
        resolved.relative_to(root.resolve())
    except Exception:
        return {"path": path, "error": "path outside workspace", "source": "workspace"}
    if not file_path.exists():
        return {"path": path, "error": "file not found", "source": "workspace"}
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
