"""Conversation Miner — auto-extract memories from raw Honcho events.

P1 Optimization: Extract structured memories from Honcho events using
FTS5 pattern matching + entity extraction. References MemPalace v3.4.1
convo_miner.py pattern.

Scans honcho_events for high-signal patterns (decisions, preferences,
blockers, workflows) and auto-creates curated memory records.

Upgraded P1-1: NLP entity extraction + relation extraction for richer
memory content.

Usage:
    from super_memory.conversation_miner import run_conversation_mining
    result = run_conversation_mining(store, dry_run=True)
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .config import load_config
from .storage import SuperMemoryStore

# ── Signal patterns ──────────────────────────────────────────────

_DECISION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(decide|decided|decision|chose|chosen|go with|pick|picked|selected)\b", re.IGNORECASE),
    re.compile(r"\b(we should|we will|let's use|going to use|prefer to)\b", re.IGNORECASE),
    re.compile(r"\b(the best approach|the right way|better to|rather than)\b", re.IGNORECASE),
]

_PREFERENCE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(prefer|preferred|preference|like|liked|favorite|favourite)\b", re.IGNORECASE),
    re.compile(r"\b(I use|I love|I hate|I want|I need|I like)\b", re.IGNORECASE),
    re.compile(r"\b(works better|easier to|more comfortable|happy with)\b", re.IGNORECASE),
]

_BLOCKER_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(block|blocked|blocker|stuck|cannot|can't|waiting for|depends on)\b", re.IGNORECASE),
    re.compile(r"\b(issue|bug|error|fail|failed|broken|not working)\b", re.IGNORECASE),
    re.compile(r"\b(need help|need input|waiting on|pending review)\b", re.IGNORECASE),
]

_WORKFLOW_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(step|steps|process|workflow|procedure|pipeline)\b", re.IGNORECASE),
    re.compile(r"\b(first|then|next|finally|repeat|loop|when.*then)\b", re.IGNORECASE),
    re.compile(r"\b(how to|guide|tutorial|setup|configure|install)\b", re.IGNORECASE),
]

_LESSON_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(learn|learned|lesson|takeaway|key insight)\b", re.IGNORECASE),
    re.compile(r"\b(tricky|hard to find|spent hours|wasted time)\b", re.IGNORECASE),
    re.compile(r"\b(remember to|don't forget|note to self|important)\b", re.IGNORECASE),
]

# ── NLP Entity Patterns (P1-1 upgrade) ──────────────────────────

_ENTITY_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(Python|FastAPI|React|Vue|Angular|Django|Flask|Node\.?js|TypeScript|Go|Rust|Swift|Kotlin|Docker|Kubernetes|AWS|GCP|Azure|PostgreSQL|MySQL|MongoDB|Redis|GraphQL|REST|gRPC)\b", re.IGNORECASE),
    re.compile(r"\b(GitHub|GitLab|Jira|Slack|Notion|VSCode|PyCharm|OpenAI|Claude|Gemini|LangChain|LlamaIndex)\b", re.IGNORECASE),
    re.compile(r"\b(microservice|monolith|serverless|event.?driven|CQRS|DDD|TDD|CI/?CD|MVP|API|SDK|ORM)\b", re.IGNORECASE),
    re.compile(r"\b(engineer|developer|designer|manager|stakeholder|customer|user|client|team)\b", re.IGNORECASE),
]

PATTERN_MAP: list[tuple[str, list[re.Pattern], str]] = [
    ("decision", _DECISION_PATTERNS, "decision"),
    ("preference", _PREFERENCE_PATTERNS, "preference"),
    ("blocker", _BLOCKER_PATTERNS, "blocker"),
    ("workflow", _WORKFLOW_PATTERNS, "workflow"),
    ("lesson", _LESSON_PATTERNS, "lesson"),
]


def _classify(text: str) -> tuple[str | None, str | None]:
    """Classify text by pattern matching. Returns (memory_type, pattern_class)."""
    text_lower = text.lower()
    for class_name, patterns, memory_type in PATTERN_MAP:
        for pat in patterns:
            if pat.search(text_lower):
                return (memory_type, class_name)
    return (None, None)


# ── NLP Entity Extraction (P1-1 upgrade) ────────────────────────

def _extract_entities_nlp(text: str) -> list[str]:
    """Extract named entities from text using regex patterns."""
    found: set[str] = set()
    for pat in _ENTITY_PATTERNS:
        matches = pat.findall(text)
        for m in matches:
            found.add(m.strip().rstrip('.'))
    return sorted(found)


def _extract_relations_nlp(text: str, entities: list[str]) -> list[tuple[str, str, str]]:
    """Extract subject-relation-object triples from text."""
    rels: list[tuple[str, str, str]] = []
    causal = re.findall(
        r"(\w+(?:\s+\w+)?)\s+(caused|broke|fixed|enables|depends on|requires|triggers|creates|blocks|uses)\s+(\w+(?:\s+\w+)?)",
        text, re.IGNORECASE,
    )
    for a, r, b in causal:
        rels.append((a.strip(), r, b.strip()))
    return rels


def _extract_key_sentence(text: str, max_len: int = 200) -> str:
    """Extract the most signal-rich sentence from text.

    Uses entity density + pattern density scoring (NLP-enhanced).
    Prefers sentences with named entities and signal patterns.
    """
    sentences = re.split(r'[.!?\n]+', text)
    best_sentence = ""
    best_score = 0
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 10:
            continue
        score = 0
        for _, patterns, _ in PATTERN_MAP:
            for pat in patterns:
                if pat.search(sent.lower()):
                    score += 2
        entities = _extract_entities_nlp(sent)
        score += len(entities) * 3
        if 20 <= len(sent) <= 120:
            score += 1
        if score > best_score:
            best_score = score
            best_sentence = sent
    if not best_sentence:
        best_sentence = text[:max_len]
    return best_sentence[:max_len].strip()


def _dedupe_candidate(
    conn: sqlite3.Connection,
    content: str,
    agent_id: str,
    threshold: float = 0.6,
) -> bool:
    """Check if a similar memory already exists (Jaccard-based with pre-filter).

    Optimized: uses content_hash for exact dedup first, then Jaccard.
    Falls back gracefully when no precomputed tokens exist.
    """
    tokens_new = set(re.findall(r"\w{3,}", content.lower()))
    if not tokens_new:
        return True

    # Exact dedup by content_hash
    import hashlib
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    existing = conn.execute(
        "SELECT content, content_hash FROM memories WHERE agent_id = ? AND LENGTH(content) > 20 ORDER BY created_at DESC LIMIT 30",
        (agent_id,),
    ).fetchall()
    seen_exact = set()
    for row in existing:
        ch = row["content_hash"] or hashlib.sha256((row["content"] or "").encode()).hexdigest()[:16]
        seen_exact.add(ch)
    if content_hash in seen_exact:
        return True  # Exact duplicate

    # Jaccard with early exit
    for row in existing:
        existing_tokens = set(re.findall(r"\w{3,}", (row["content"] or "").lower()))
        if not existing_tokens:
            continue
        intersection = tokens_new & existing_tokens
        union = tokens_new | existing_tokens
        jaccard = len(intersection) / len(union)
        if jaccard >= threshold:
            return True
    return False


def run_conversation_mining(
    store: SuperMemoryStore,
    dry_run: bool = True,
    limit: int = 100,
    min_content_length: int = 30,
) -> dict[str, Any]:
    """Scan Honcho events and auto-extract memories.

    Strategy:
      1. Fetch recent honcho_events not yet mined
      2. Classify each by pattern type (decision/preference/blocker/workflow/lesson)
      3. NLP entity extraction for richer content
      4. Deduplicate against existing memories
      5. Auto-create curated memory records

    Args:
        store: SuperMemoryStore instance
        dry_run: If True, only report what would be created
        limit: Max events to scan
        min_content_length: Skip events shorter than this

    Returns:
        Dict with stats and candidate memories
    """
    from . import bridge
    from .models import MemoryScope

    now = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "scanned": 0,
        "classified": 0,
        "deduped": 0,
        "created": 0,
        "candidates": [],
    }

    with store.connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row

        conn.execute(
            "CREATE TABLE IF NOT EXISTS lifecycle_state (key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        last_mined_row = conn.execute(
            "SELECT payload_json FROM lifecycle_state WHERE key = 'conversation_mining_cursor'"
        ).fetchone()
        last_mined_id = ""
        if last_mined_row:
            try:
                last_mined_id = json.loads(last_mined_row["payload_json"]).get("last_event_id", "")
            except Exception:
                pass

        if last_mined_id:
            rows = conn.execute(
                "SELECT * FROM honcho_events WHERE id > ? AND LENGTH(content) >= ? ORDER BY created_at ASC LIMIT ?",
                (last_mined_id, min_content_length, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM honcho_events WHERE LENGTH(content) >= ? ORDER BY created_at ASC LIMIT ?",
                (min_content_length, limit),
            ).fetchall()

        report["scanned"] = len(rows)
        last_id = last_mined_id

        for row in rows:
            rd = dict(row)
            content = rd.get("content") or ""
            agent_id = rd.get("observer_peer_id") or "lucas"
            session_id = rd.get("session_id") or ""
            event_id = rd["id"]

            memory_type, pattern_class = _classify(content)
            if not memory_type:
                continue

            report["classified"] += 1

            if _dedupe_candidate(conn, content, agent_id, threshold=0.6):
                report["deduped"] += 1
                continue

            key_sent = _extract_key_sentence(content, max_len=200)
            entities = _extract_entities_nlp(content)
            relations = _extract_relations_nlp(content, entities)

            candidate = {
                "event_id": event_id,
                "agent_id": agent_id,
                "session_id": session_id,
                "type": memory_type,
                "pattern_class": pattern_class,
                "content": key_sent,
                "entities": entities,
                "relations": relations,
                "original_length": len(content),
            }
            report["candidates"].append(candidate)
            last_id = event_id

            if not dry_run:
                tags = ["mined", f"pattern:{pattern_class}", f"source:honcho_event"]
                if session_id:
                    tags.append(f"session:{session_id[:8]}")
                metadata: dict[str, Any] = {
                    "mined_from_event": event_id,
                    "pattern_class": pattern_class,
                    "original_length": len(content),
                }
                if entities:
                    metadata["mined_entities"] = entities
                if relations:
                    metadata["mined_relations"] = relations

                saved = bridge.remember(
                    {
                        "content": key_sent,
                        "type": memory_type,
                        "scope": MemoryScope.PROJECT.value,
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "tags": tags,
                        "source": "super-memory.conversation_miner",
                        "trust_score": 0.6,
                        "metadata": metadata,
                    }
                )
                if saved.get("record"):
                    report["created"] += 1

        if not dry_run and last_id != last_mined_id:
            conn.execute(
                "INSERT OR REPLACE INTO lifecycle_state (key, payload_json, updated_at) VALUES (?, ?, ?)",
                ("conversation_mining_cursor", json.dumps({"last_event_id": last_id}), now),
            )
            conn.commit()

    return report
