"""Session-scoped visibility filtering for search results.

Matches OpenClaw memory-core session-search-visibility:
- Results from the current session are boosted
- Results from other sessions are not excluded but ranked lower
- Session context extracted from caller metadata or path
"""

from __future__ import annotations

import re
from typing import Any


# ── Session Boost ──────────────────────────────────────────────────────────


def boost_current_session(
    results: list[dict[str, Any]],
    current_session_id: str | None = None,
    *,
    boost_factor: float = 0.3,
    score_key: str = "score",
    session_id_key: str = "session_id",
) -> list[dict[str, Any]]:
    """Boost results from the current session, leave others unchanged.

    Args:
        results: Search result dicts
        current_session_id: Current session identifier (None = no boost)
        boost_factor: Additive boost to score (default 0.3)
        score_key: Dict key for score (mutated in place)
        session_id_key: Dict key for session ID

    Returns:
        Same list with boosted scores (in-place)
    """
    if not current_session_id or not results:
        return results

    csid = str(current_session_id).strip()
    for item in results:
        item_sid = _extract_session_id(item, session_id_key)
        if item_sid and item_sid == csid:
            current_score = max(0.0, min(1.0, item.get(score_key, 0.0)))
            item["_session_boost"] = boost_factor
            item[score_key] = min(1.0, current_score + boost_factor)
            item["_session_match"] = True
        else:
            item["_session_match"] = False

    return results


def _extract_session_id(item: dict[str, Any], key: str) -> str | None:
    """Extract session ID from result dict, checking multiple locations."""
    # Direct key
    raw = item.get(key)
    if raw and isinstance(raw, str):
        return raw

    # From citation field (e.g., "project · session:abc123...")
    citation = item.get("citation", "")
    if citation:
        m = re.search(r'session:([a-f0-9]{8,})', citation)
        if m:
            return m.group(1)

    # From path containing session identifier
    path = item.get("path", "")
    m = re.search(r'/sessions?/([^/]+?)(?:/|$|\.)', path)
    if m:
        return m.group(1)

    return None


# ── Session metadata enrichment ────────────────────────────────────────────


def annotate_session_info(
    results: list[dict[str, Any]],
    current_session_id: str | None = None,
) -> list[dict[str, Any]]:
    """Add session metadata annotations to each result."""
    for item in results:
        item["_session_id"] = _extract_session_id(item, "session_id") or ""
        item["_is_current_session"] = (
            current_session_id is not None
            and item["_session_id"] == str(current_session_id)
        )
    return results
