"""Async enrichment deriver — non-blocking post-save enrichment pipeline.

P2 #7 Optimization: Queue-based post-save entity extraction + summarization +
relation detection. Non-blocking pipeline that avoids delaying the save response.

References Honcho v3.0.9 deriver architecture (async enrichment queue).

Pipeline stages:
  1. Entity extraction (named entities, key phrases)
  2. Relation detection (causal, comparative, sequential)
  3. Summarization (extractive key-sentence)
  4. Affect classification (arousal, valence)
  5. Semantic indexing (sqlite-vec)

Usage:
    from super_memory.deriver import enrich_async, flush_deriver_queue
    enrich_async(memory_id, content, config_path)
    flush_deriver_queue(config_path)
"""

from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import load_config

logger = logging.getLogger("super-memory.deriver")

# ── Per-thread queue ──────────────────────────────────────────────

_QUEUES: dict[str, list[dict[str, Any]]] = {}
_QUEUE_LOCKS: dict[str, threading.Lock] = {}
_BACKGROUND_WORKERS: dict[str, threading.Thread] = {}


@dataclass
class EnrichmentResult:
    memory_id: str
    entities: list[str] = field(default_factory=list)
    relations: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    arousal: float = 0.0
    valence: str = "neutral"
    indexed: bool = False
    embedded: bool = False
    error: str = ""


# ── Enrichment helpers (non-blocking, best-effort) ────────────────


def _extract_entities(text: str, max_entities: int = 10) -> list[str]:
    """Extract named entities using regex/heuristic patterns.

    Picks capitalized multi-word phrases, email-like patterns,
    and known tech keywords. No LLM dependency.
    """
    import re

    entities: list[str] = []
    seen: set[str] = set()

    # Pattern 1: Capitalized multi-word phrases (projects, people, orgs)
    for match in re.finditer(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){0,3}\b", text):
        phrase = match.group().strip()
        # Skip sentences (too long)
        if len(phrase) > 60 or len(phrase.split()) > 6:
            continue
        if phrase.lower() not in seen:
            seen.add(phrase.lower())
            entities.append(phrase)

    # Pattern 2: Known tech/tool keywords (lowercase but entity-worthy)
    tech_keywords = re.findall(
        r"\b(python|javascript|typescript|react|vue|angular|docker|kubernetes|"
        r"sqlite|postgres|mysql|redis|mongodb|ollama|openai|gemini|claude|"
        r"fastapi|flask|django|pytorch|tensorflow|pytest|git|github|ci/cd)\b",
        text,
        re.IGNORECASE,
    )
    for kw in tech_keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            entities.append(kw.lower())

    return entities[:max_entities]


def _detect_relations(text: str) -> list[dict[str, str]]:
    """Detect basic relations (causes, depends_on, related_to)."""
    import re

    relations: list[dict[str, str]] = []

    # "X because Y" / "X caused Y"
    cause_match = re.search(r"\b(because|caused|leads to|results in)\s+(.+?)[.]", text, re.IGNORECASE)
    if cause_match and len(cause_match.group(0)) < 200:
        relations.append({"type": "causes", "text": cause_match.group(0).strip()})

    # "X depends on Y"
    dep_match = re.search(r"\b(depends on|requires|needs)\s+(.+?)[.]", text, re.IGNORECASE)
    if dep_match and len(dep_match.group(0)) < 200:
        relations.append({"type": "depends_on", "text": dep_match.group(0).strip()})

    # "X relates to Y"
    rel_match = re.search(r"\b(relates to|connected to|associated with)\s+(.+?)[.]", text, re.IGNORECASE)
    if rel_match and len(rel_match.group(0)) < 200:
        relations.append({"type": "related_to", "text": rel_match.group(0).strip()})

    return relations


def _extractive_summary(text: str, max_sentences: int = 2) -> str:
    """Extractive summary — pick key sentences by pattern density."""
    import re

    if len(text) <= 200:
        return text

    sentences = re.split(r"[.!?\n]+", text)
    scored: list[tuple[float, str, int]] = []

    for idx, sent in enumerate(sentences):
        sent = sent.strip()
        if len(sent) < 20:
            continue
        score = 0.0
        # Prefer sentences with signal words
        signal_words = r"\b(decide|important|key|critical|must|should|need|requires|fix|bug|error|blocker|solution|result)\b"
        signals = len(re.findall(signal_words, sent, re.IGNORECASE))
        score += signals * 2.0
        # Prefer medium length (40-150 chars)
        if 40 <= len(sent) <= 150:
            score += 1.0
        # Prefer first sentence (often the topic)
        if idx == 0:
            score += 1.5
        scored.append((score, sent, idx))

    scored.sort(key=lambda x: (-x[0], x[2]))
    selected = [s[1] for s in scored[:max_sentences]]
    return ". ".join(selected) + ("." if selected else text[:150])


# ── Pipeline execution ────────────────────────────────────────────


def run_deriver_pipeline(
    memory_id: str,
    content: str,
    config_path: str | None = None,
) -> EnrichmentResult:
    """Run the full enrichment pipeline for a single memory.

    Non-blocking, best-effort — errors are captured but never thrown.
    """
    result = EnrichmentResult(memory_id=memory_id)

    try:
        # Stage 1: Entity extraction
        entities = _extract_entities(content)
        result.entities = entities
    except Exception as exc:
        result.error += f"entities:{exc}; "

    try:
        # Stage 2: Relation detection
        relations = _detect_relations(content)
        result.relations = relations
    except Exception as exc:
        result.error += f"relations:{exc}; "

    try:
        # Stage 3: Extractive summary
        summary = _extractive_summary(content)
        result.summary = summary
    except Exception as exc:
        result.error += f"summary:{exc}; "

    try:
        # Stage 4: Affect classification
        from .affect import classify_affect
        affect = classify_affect({"text": content})
        if isinstance(affect, dict):
            result.arousal = affect.get("arousal", 0.0) or 0.0
            result.valence = affect.get("valence", "neutral") or "neutral"
    except Exception as exc:
        result.error += f"affect:{exc}; "

    try:
        # Stage 5: Update memory metadata with enrichment results
        cfg = load_config(config_path)
        from .storage import SuperMemoryStore
        store = SuperMemoryStore(cfg)
        with store.connect() as conn:
            meta_raw = conn.execute(
                "SELECT metadata_json FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
            if meta_raw:
                meta = json.loads(meta_raw["metadata_json"] or "{}")
                meta["entities"] = entities[:5]
                meta["summary"] = summary[:200]
                meta["arousal"] = result.arousal
                meta["valence"] = result.valence
                if relations:
                    meta["relations"] = relations
                conn.execute(
                    "UPDATE memories SET metadata_json = ? WHERE id = ?",
                    (json.dumps(meta, ensure_ascii=False), memory_id),
                )
                conn.commit()
                result.indexed = True
    except Exception as exc:
        result.error += f"update_meta:{exc}; "

    try:
        # Stage 6 (E8): semantic embedding — write vector for the ACTIVE
        # workspace_markdown row so semantic recall has data. Runs here in the
        # background deriver worker so save() never blocks on the embed call.
        cfg = load_config(config_path)
        if getattr(cfg, "vector_enabled", False):
            from .vector import VectorStore, embed_text
            vec = embed_text(content, config=cfg)
            if vec:
                VectorStore(cfg).add_embedding(memory_id, vec)
                result.embedded = True
    except Exception as exc:
        result.error += f"embed:{exc}; "

    return result


# ── Queue management ──────────────────────────────────────────────


def _ensure_queue(config_path: str | None = None) -> tuple[str, list[dict[str, Any]], threading.Lock]:
    key = config_path or "default"
    if key not in _QUEUES:
        _QUEUES[key] = []
        _QUEUE_LOCKS[key] = threading.Lock()
    return key, _QUEUES[key], _QUEUE_LOCKS[key]


def enrich_async(
    memory_id: str,
    content: str,
    config_path: str | None = None,
) -> None:
    """Enqueue a memory for async enrichment.

    Returns immediately. The deriver pipeline runs in a background thread.
    """
    key, queue, lock = _ensure_queue(config_path)
    with lock:
        queue.append({"memory_id": memory_id, "content": content})
    # Start background worker if not already running
    if key not in _BACKGROUND_WORKERS or not _BACKGROUND_WORKERS[key].is_alive():
        worker = threading.Thread(
            target=_background_worker,
            args=(key, config_path),
            daemon=True,
            name=f"deriver-{key[:8]}",
        )
        worker.start()
        _BACKGROUND_WORKERS[key] = worker
        logger.info("Deriver worker started for queue '%s'", key)


def flush_deriver_queue(config_path: str | None = None, max_items: int = 50) -> int:
    """Synchronously flush the deriver queue — process up to max_items items.

    Returns count of items processed. Useful for testing or shutdown.
    """
    key, queue, lock = _ensure_queue(config_path)
    processed = 0
    while processed < max_items:
        with lock:
            if not queue:
                break
            item = queue.pop(0)
        try:
            run_deriver_pipeline(item["memory_id"], item["content"], config_path)
            processed += 1
        except Exception as exc:
            logger.warning("Deriver flush item %s failed: %s", item["memory_id"], exc)
    logger.info("Deriver flush: %d items processed", processed)
    return processed


def deriver_queue_size(config_path: str | None = None) -> int:
    """Return the current size of the deriver queue."""
    key, queue, _ = _ensure_queue(config_path)
    return len(queue)


def _background_worker(queue_key: str, config_path: str | None = None) -> None:
    """Background thread that processes the deriver queue."""
    import time

    max_batch = 5
    while True:
        key, queue, lock = _ensure_queue(config_path)
        if key != queue_key:
            break  # Queue was replaced
        with lock:
            items_to_process = queue[:max_batch]
            del queue[:max_batch]
        for item in items_to_process:
            try:
                run_deriver_pipeline(item["memory_id"], item["content"], config_path)
            except Exception as exc:
                logger.warning("Deriver worker item %s failed: %s", item["memory_id"], exc)
        if not items_to_process:
            break  # Queue empty, worker exits
        time.sleep(0.1)  # Yield between batches
