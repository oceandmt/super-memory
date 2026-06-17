"""BM25 Hybrid Search — keyword + relevance scoring for MemPalace drawer search.

Pure Python BM25 implementation. No ChromaDB, no embeddings, no network.
Scores drawers stored in SQLite against text queries.

Design:
  - BM25 scoring (TF, IDF, doc-length normalization)
  - Tokenize with word-boundary regex (≥2 char tokens)
  - Hybrid: exact keyword match as floor, BM25 as ranking signal
  - Return ranked results with scores and metadata

Inspired by mempalace/mempalace searcher.py (upstream v3.4.1)
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"\w{2,}", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """Lowercase + strip to alphanumeric tokens of length ≥ 2."""
    if not text:
        return []
    return _TOKEN_RE.findall(text.lower())


def _bm25_scores(
    query: str,
    documents: list[str],
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """Compute Okapi-BM25 scores for query against each document.

    IDF computed over the provided corpus using smoothed formula:
        log((N - df + 0.5) / (df + 0.5) + 1)

    Parameters:
        k1 — term-frequency saturation (default 1.5)
        b  — length normalization (default 0.75)

    Returns list of scores in same order as documents.
    """
    n_docs = len(documents)
    query_terms = set(_tokenize(query))
    if not query_terms or n_docs == 0:
        return [0.0] * n_docs

    tokenized = [_tokenize(d) for d in documents]
    doc_lens = [len(toks) for toks in tokenized]
    if not any(doc_lens):
        return [0.0] * n_docs
    avgdl = sum(doc_lens) / n_docs or 1.0

    # Document frequency
    df: dict[str, int] = {term: 0 for term in query_terms}
    for toks in tokenized:
        seen = set(toks) & query_terms
        for term in seen:
            df[term] += 1

    idf: dict[str, float] = {
        term: math.log((n_docs - df[term] + 0.5) / (df[term] + 0.5) + 1)
        for term in query_terms
    }

    scores: list[float] = []
    for toks, dl in zip(tokenized, doc_lens):
        if dl == 0:
            scores.append(0.0)
            continue
        tf: dict[str, int] = {}
        for t in toks:
            if t in query_terms:
                tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for term, freq in tf.items():
            num = freq * (k1 + 1)
            den = freq + k1 * (1 - b + b * dl / avgdl)
            score += idf[term] * num / den
        scores.append(score)
    return scores


def _keyword_exact_score(query: str, document: str) -> float:
    """Simple exact keyword match score (0.0 to 1.0).

    Fraction of query tokens found verbatim in document.
    """
    query_terms = set(_tokenize(query))
    if not query_terms:
        return 0.0
    doc_lower = document.lower()
    hits = sum(1 for t in query_terms if t in doc_lower)
    return hits / len(query_terms)


def search_sqlite(
    db_path: Path | str,
    query: str,
    wing: str | None = None,
    room: str | None = None,
    limit: int = 10,
    keyword_weight: float = 0.3,
    bm25_weight: float = 0.7,
) -> dict[str, Any]:
    """Search drawers in SQLite palace database using BM25 + keyword hybrid.

    Args:
        db_path: Path to super_memory SQLite database
        query: Search query string
        wing: Optional wing filter
        room: Optional room filter
        limit: Max results to return
        keyword_weight: Weight for exact keyword match (0-1)
        bm25_weight: Weight for BM25 score (0-1)

    Returns:
        Dict with query, filters, results list
    """
    import sqlite3

    db = Path(db_path)
    if not db.exists():
        return {"error": f"Database not found: {db_path}", "results": []}

    conn = sqlite3.connect(str(db), timeout=10)
    conn.row_factory = sqlite3.Row

    try:
        # Build WHERE clause
        where_parts = ["1=1"]
        params: list[Any] = []
        if wing:
            where_parts.append("wing = ?")
            params.append(wing)
        if room:
            where_parts.append("room = ?")
            params.append(room)

        where_clause = " AND ".join(where_parts)

        # Fetch all candidate drawers
        rows = conn.execute(
            f"SELECT id, wing, room, hall, content, source_file, created_at "
            f"FROM palace_drawers WHERE {where_clause} ORDER BY created_at DESC",
            params,
        ).fetchall()

        if not rows:
            return {
                "query": query,
                "filters": {"wing": wing, "room": room},
                "total": 0,
                "results": [],
            }

        documents = [row["content"] or "" for row in rows]

        # Compute scores
        keyword_scores = [_keyword_exact_score(query, doc) for doc in documents]
        bm25_raw = _bm25_scores(query, documents)
        max_bm25 = max(bm25_raw) if bm25_raw else 1.0

        # Hybrid scoring
        scored: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            kw = keyword_scores[i]
            bm = bm25_raw[i] / max_bm25 if max_bm25 > 0 else 0.0
            hybrid = keyword_weight * kw + bm25_weight * bm

            if hybrid > 0.001:  # Skip zero-score results
                scored.append({
                    "id": row["id"],
                    "wing": row["wing"] or "",
                    "room": row["room"] or "",
                    "hall": row["hall"] or "",
                    "text": (row["content"] or "")[:500],
                    "source_file": Path(row["source_file"] or "?").name if row["source_file"] else "?",
                    "created_at": row["created_at"] or "",
                    "keyword_score": round(kw, 3),
                    "bm25_score": round(bm25_raw[i], 3),
                    "hybrid_score": round(hybrid, 3),
                })

        scored.sort(key=lambda x: x["hybrid_score"], reverse=True)
        results = scored[:limit]

        return {
            "query": query,
            "filters": {"wing": wing, "room": room},
            "total": len(rows),
            "matched": len(scored),
            "returned": len(results),
            "results": results,
        }

    finally:
        conn.close()


def find_similar_drawers(
    db_path: Path | str,
    drawer_id: str,
    wing: str | None = None,
    limit: int = 5,
    threshold: float = 0.2,
) -> dict[str, Any]:
    """Find drawers similar to a given drawer using Jaccard token similarity.

    Args:
        db_path: Path to super_memory SQLite database
        drawer_id: ID of the reference drawer
        wing: Optional wing filter
        limit: Max results
        threshold: Minimum Jaccard similarity (0-1)

    Returns:
        Dict with reference drawer and similar results
    """
    import sqlite3

    db = Path(db_path)
    if not db.exists():
        return {"error": f"Database not found: {db_path}", "results": []}

    conn = sqlite3.connect(str(db), timeout=10)
    conn.row_factory = sqlite3.Row

    try:
        # Get reference drawer
        ref = conn.execute(
            "SELECT id, wing, room, content FROM palace_drawers WHERE id = ?",
            (drawer_id,),
        ).fetchone()

        if not ref:
            return {"error": f"Drawer not found: {drawer_id}", "results": []}

        ref_tokens = set(_tokenize(ref["content"] or ""))

        # Get candidates
        where_parts = ["id != ?"]
        params: list[Any] = [drawer_id]
        if wing:
            where_parts.append("wing = ?")
            params.append(wing)

        rows = conn.execute(
            f"SELECT id, wing, room, content, source_file, created_at "
            f"FROM palace_drawers WHERE {' AND '.join(where_parts)} "
            f"ORDER BY created_at DESC LIMIT 500",
            params,
        ).fetchall()

        if not ref_tokens:
            return {
                "reference": {"id": ref["id"], "wing": ref["wing"], "room": ref["room"]},
                "similar": [],
            }

        scored: list[dict[str, Any]] = []
        for row in rows:
            cand_tokens = set(_tokenize(row["content"] or ""))
            if not cand_tokens:
                continue

            intersection = ref_tokens & cand_tokens
            union = ref_tokens | cand_tokens
            jaccard = len(intersection) / len(union) if union else 0.0

            if jaccard >= threshold:
                scored.append({
                    "id": row["id"],
                    "wing": row["wing"] or "",
                    "room": row["room"] or "",
                    "text": (row["content"] or "")[:300],
                    "source_file": Path(row["source_file"] or "?").name if row["source_file"] else "?",
                    "created_at": row["created_at"] or "",
                    "jaccard_similarity": round(jaccard, 3),
                })

        scored.sort(key=lambda x: x["jaccard_similarity"], reverse=True)

        return {
            "reference": {
                "id": ref["id"],
                "wing": ref["wing"],
                "room": ref["room"],
                "text": (ref["content"] or "")[:300],
            },
            "total_candidates": len(rows),
            "similar_count": len(scored),
            "similar": scored[:limit],
        }

    finally:
        conn.close()


# ── Command-line ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python searcher.py <db_path> <query> [wing] [room] [limit]")
        sys.exit(1)

    db_path = sys.argv[1]
    query = sys.argv[2]
    wing = sys.argv[3] if len(sys.argv) > 3 else None
    room = sys.argv[4] if len(sys.argv) > 4 else None
    limit = int(sys.argv[5]) if len(sys.argv) > 5 else 10

    result = search_sqlite(db_path, query, wing=wing, room=room, limit=limit)
    import json

    print(json.dumps(result, indent=2, ensure_ascii=False))
