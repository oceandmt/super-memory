"""Conversation Miner — ingest chat conversations into the palace.

Ingests chat exports (plain text, JSON, JSONL, Slack, ChatGPT, Claude Code
exports). Normalizes format, chunks by message exchange pairs (Q+A = one unit),
and stores as palace drawers.

Same palace as regular drawer storage. Different ingest strategy.
Uses collision_scan.py to prevent duplicate writes.

Usage:
    from super_memory.mempalace.convo_miner import mine_conversation, mine_directory

    # Mine a single file
    mine_conversation(db_path, "chat_export.json", wing="direct-main")

    # Mine all conversation files in a directory
    result = mine_directory(db_path, "exports/", wing="brain-main")
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .collision_scan import assert_no_collisions

# ── Constants ───────────────────────────────────────────────────────────────

CONVO_EXTENSIONS = {".txt", ".md", ".json", ".jsonl"}
CHUNK_SIZE = 800  # chars per drawer
MIN_CHUNK_SIZE = 30  # minimum chars to create a drawer
BATCH_SIZE = 100
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# ── Hall keyword detection ──────────────────────────────────────────────────

DEFAULT_HALL_KEYWORDS: dict[str, list[str]] = {
    "facts": ["fact", "actually", "true", "happened", "real", "confirmed"],
    "events": ["today", "yesterday", "happened", "occurred", "event"],
    "decisions": ["decided", "decision", "agreed", "confirmed", "final", "we'll", "let's do"],
    "questions": ["what", "how", "why", "when", "where", "who", "?"],
    "plans": ["plan", "planning", "schedule", "tomorrow", "next", "upcoming"],
    "reflections": ["feel", "think", "wonder", "maybe", "perhaps", "reflect"],
    "technical": ["code", "deploy", "bug", "fix", "api", "config", "build"],
}


def _detect_hall(content: str, keywords: dict[str, list[str]] | None = None) -> str:
    """Route content to a hall using keyword scoring."""
    kw = keywords or DEFAULT_HALL_KEYWORDS
    content_lower = content[:3000].lower()
    scores: dict[str, int] = {}
    for hall, hall_keywords in kw.items():
        score = sum(1 for k in hall_keywords if k in content_lower)
        if score > 0:
            scores[hall] = score
    return max(scores, key=scores.get) if scores else "general"


# ── File detection ──────────────────────────────────────────────────────────

_MESSAGE_PATTERNS = [
    re.compile(r'^\[(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)\]\s*(\w[\w.-]*):\s*(.*)'),
    re.compile(r'^(\w[\w.-]*)\s*[-:]\s*(.*)'),  # "Lucas - hello" or "Max: hey"
    re.compile(r'^(\d{2}:\d{2})\s*[-–]\s*(\w[\w.-]*):\s*(.*)'),  # "14:22 - Lucas: hello"
    re.compile(r'^<(\w[\w.-]*)>\s*(.*)'),  # "<Lucas> hello"
]

_SLACK_PATTERN = re.compile(r'"text":\s*"((?:[^"\\]|\\")+)"')
_CHATGPT_Q_PATTERN = re.compile(r'"message":\s*\{[^}]*"content":\s*\{[^}]*"parts":\s*\["([^"]*)"')
_CHATGPT_A_PATTERN = re.compile(r'"message":\s*\{[^}]*"content":\s*"([^"]*)"')

_JSON_ROLE_KEYWORDS = {"user", "assistant", "human", "ai", "bot", "agent", "system", "speaker", "from", "sender"}


def _detect_format(file_path: Path) -> str:
    """Detect conversation file format."""
    suffix = file_path.suffix.lower()
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".json":
        try:
            data = json.loads(file_path.read_text()[:10000])
            if isinstance(data, list):
                for item in data[:3]:
                    if isinstance(item, dict):
                        for k in item:
                            if k.lower() in _JSON_ROLE_KEYWORDS:
                                return "chatgpt"  # ChatGPT/Claude export
                        return "json_array"
            return "json"
        except json.JSONDecodeError:
            return "plain"
    return "plain"


# ── Message parsing ─────────────────────────────────────────────────────────


def _parse_messages_plain(text: str) -> list[dict[str, Any]]:
    """Parse plain text conversation into messages."""
    messages: list[dict[str, Any]] = []
    current = None

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        matched = False
        for pat in _MESSAGE_PATTERNS:
            m = pat.match(line)
            if m:
                groups = m.groups()
                if len(groups) == 3:
                    ts, speaker, msg = groups
                elif len(groups) == 2:
                    speaker, msg = groups
                    ts = ""
                else:
                    continue

                if current:
                    messages.append(current)
                current = {"speaker": speaker.strip(), "timestamp": _normalize_ts(ts), "content": msg.strip()}
                matched = True
                break

        if not matched and current:
            current["content"] += " " + line

    if current:
        messages.append(current)

    return messages


def _parse_messages_jsonl(text: str) -> list[dict[str, Any]]:
    """Parse JSONL conversation format."""
    messages: list[dict[str, Any]] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            speaker = ""
            content = ""
            ts = ""

            for k in _JSON_ROLE_KEYWORDS:
                if k in obj:
                    speaker = str(obj[k])
                    break
            for k in ("content", "text", "message", "body"):
                if k in obj:
                    content = str(obj[k])
                    break
            for k in ("timestamp", "created_at", "ts", "time"):
                if k in obj:
                    ts = str(obj[k])
                    break

            if content and speaker:
                messages.append({"speaker": speaker, "timestamp": _normalize_ts(ts), "content": content})
        except json.JSONDecodeError:
            continue
    return messages


def _parse_messages_chatgpt(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse ChatGPT/Claude export format."""
    messages: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        speaker = ""
        content = ""
        for k in _JSON_ROLE_KEYWORDS:
            if k in item:
                v = item[k]
                if isinstance(v, str):
                    speaker = v
                    break

        for k in ("content", "text", "message", "body"):
            v = item.get(k)
            if isinstance(v, str):
                content = v
                break
            elif isinstance(v, dict):
                for inner_k in ("parts", "text", "body"):
                    inner = v.get(inner_k)
                    if isinstance(inner, list):
                        content = " ".join(str(x) for x in inner if isinstance(x, str))
                        break
                    elif isinstance(inner, str):
                        content = inner
                        break
                if content:
                    break

        if content:
            messages.append({"speaker": speaker or "unknown", "timestamp": _normalize_ts(str(item.get("timestamp", ""))), "content": content})
    return messages


def _normalize_ts(ts: str) -> str:
    """Normalize timestamp to ISO format."""
    if not ts:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = None
        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%I:%M %p", "%H:%M"]:
            try:
                dt = datetime.strptime(ts, fmt)
                break
            except ValueError:
                continue
        if dt:
            return dt.replace(tzinfo=timezone.utc).isoformat()
    except (ValueError, OverflowError):
        pass
    return datetime.now(timezone.utc).isoformat()


# ── Chunking ────────────────────────────────────────────────────────────────


def _chunk_messages(messages: list[dict[str, Any]], chunk_size: int = CHUNK_SIZE) -> list[dict[str, Any]]:
    """Chunk messages into drawer-sized units.

    Groups consecutive messages from the same speaker, then splits at chunk_size.
    Adjacent Q+A pairs stay together when possible.
    """
    drawers: list[dict[str, Any]] = []
    current = ""
    current_speakers: set[str] = set()
    current_ts = ""

    for msg in messages:
        candidate = current
        if candidate:
            candidate += "\n" + f"[{msg['speaker']}]: {msg['content']}"
        else:
            candidate = f"[{msg['speaker']}]: {msg['content']}"

        if len(candidate) > chunk_size and current:
            drawers.append({
                "content": current,
                "speakers": ", ".join(sorted(current_speakers)),
                "timestamp": current_ts or msg["timestamp"],
            })
            current = f"[{msg['speaker']}]: {msg['content']}"
            current_speakers = {msg["speaker"]}
            current_ts = msg["timestamp"]
        else:
            current = candidate
            current_speakers.add(msg["speaker"])
            if not current_ts:
                current_ts = msg["timestamp"]

    if current and len(current) >= MIN_CHUNK_SIZE:
        drawers.append({
            "content": current,
            "speakers": ", ".join(sorted(current_speakers)),
            "timestamp": current_ts,
        })

    return drawers


# ── Mining ──────────────────────────────────────────────────────────────────


def _generate_drawer_id(source_file: str, chunk_index: int, content: str) -> str:
    """Generate a stable drawer_id from source + index + content hash."""
    key = f"{source_file}:{chunk_index}"
    hash_hex = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"conv-{hashlib.sha256(key.encode()).hexdigest()[:12]}-{hash_hex}"


def mine_conversation(
    db_path: Path | str,
    file_path: Path | str,
    wing: str = "conversations",
    keywords: dict[str, list[str]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mine a single conversation file into the palace.

    Args:
        db_path: Path to SQLite database
        file_path: Path to conversation file
        wing: Wing to file under
        keywords: Hall keyword mapping (uses DEFAULT_HALL_KEYWORDS if None)
        dry_run: Preview mode — don't write to DB

    Returns:
        Dict with mining stats
    """
    import sqlite3

    fp = Path(file_path)
    db = Path(db_path)

    if not fp.exists():
        return {"error": f"File not found: {file_path}"}
    if fp.stat().st_size > MAX_FILE_SIZE:
        return {"error": f"File too large: {fp.stat().st_size} bytes (max {MAX_FILE_SIZE})", "skipped": True}
    if fp.suffix.lower() not in CONVO_EXTENSIONS:
        return {"error": f"Unsupported format: {fp.suffix}", "skipped": True}

    # Read and parse
    try:
        raw = fp.read_text()
    except UnicodeDecodeError:
        try:
            raw = fp.read_bytes().decode("latin-1")
        except Exception as e:
            return {"error": f"Read error: {e}", "skipped": True}

    fmt = _detect_format(fp)
    if fmt in ("chatgpt", "json_array"):
        try:
            data = json.loads(raw)
            messages = _parse_messages_chatgpt(data)
        except json.JSONDecodeError:
            messages = _parse_messages_plain(raw)
    elif fmt == "jsonl":
        messages = _parse_messages_jsonl(raw)
    else:
        messages = _parse_messages_plain(raw)

    if not messages:
        return {"file": str(fp), "format": fmt, "messages": 0, "drawers": 0, "skipped": True}

    # Chunk
    chunks = _chunk_messages(messages)
    if not chunks:
        return {"file": str(fp), "format": fmt, "messages": len(messages), "drawers": 0, "skipped": True}

    # Build batch
    source_file = str(fp)
    now = datetime.now(timezone.utc).isoformat()
    batch: list[tuple[str, dict[str, Any]]] = []

    for i, chunk in enumerate(chunks):
        drawer_id = _generate_drawer_id(source_file, i, chunk["content"])
        hall = _detect_hall(chunk["content"], keywords)
        meta = {
            "source_file": source_file,
            "chunk_index": i,
            "created_at": chunk.get("timestamp") or now,
        }
        batch.append((drawer_id, meta))

    # Collision check
    if db.exists():
        try:
            assert_no_collisions(str(db), batch)
        except CollisionError as ce:
            # File already mined — skip
            return {"file": str(fp), "format": fmt, "messages": len(messages), "drawers": 0, "skipped": True, "reason": "already_mined"}

    if dry_run:
        return {
            "file": str(fp),
            "format": fmt,
            "messages": len(messages),
            "drawers": len(chunks),
            "wing": wing,
            "dry_run": True,
            "preview": chunks[:3],
        }

    # Insert
    conn = sqlite3.connect(str(db), timeout=30)
    try:
        conn.execute("BEGIN")
        for (drawer_id, meta), chunk in zip(batch, chunks):
            hall = _detect_hall(chunk["content"], keywords)
            conn.execute(
                """INSERT OR IGNORE INTO palace_drawers (id, wing, room, hall, content, source_file, created_at)
                   VALUES (?, ?, 'convo', ?, ?, ?, ?)""",
                (drawer_id, wing, hall, chunk["content"], source_file, meta.get("created_at", now)),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return {"error": f"Insert error: {e}"}
    finally:
        conn.close()

    return {
        "file": str(fp),
        "format": fmt,
        "messages": len(messages),
        "drawers": len(chunks),
        "wing": wing,
        "source_file": source_file,
    }


def mine_directory(
    db_path: Path | str,
    directory: Path | str,
    wing: str = "conversations",
    recursive: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mine all conversation files in a directory.

    Args:
        db_path: Path to SQLite database
        directory: Directory to scan
        wing: Wing to file under
        recursive: Scan subdirectories
        dry_run: Preview mode

    Returns:
        Dict with total stats and per-file results
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return {"error": f"Not a directory: {directory}"}

    pattern = "**/*" if recursive else "*"
    files = [f for f in sorted(dir_path.glob(pattern)) if f.is_file() and f.suffix.lower() in CONVO_EXTENSIONS]

    results: list[dict[str, Any]] = []
    total_messages = 0
    total_drawers = 0
    skipped = 0

    for f in files:
        result = mine_conversation(db_path, f, wing=wing, dry_run=dry_run)
        results.append(result)
        if not result.get("skipped"):
            total_messages += result.get("messages", 0)
            total_drawers += result.get("drawers", 0)
        else:
            skipped += 1

    return {
        "files_processed": len(files),
        "files_skipped": skipped,
        "total_messages": total_messages,
        "total_drawers": total_drawers,
        "wing": wing,
        "results": results[:20],  # Limit output
    }


# ── Auto-detect entities from conversation ──────────────────────────────────


def detect_entities_from_convo(messages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Scan parsed messages for entity mentions.

    Returns dict with 'people', 'projects', 'mentions' lists.
    """
    from .entity_detector import scan_text

    all_text = " ".join(m.get("content", "") for m in messages)
    detections = scan_text(all_text)

    people = [d for d in detections if d["kind"] == "person" and d["confidence"] >= 0.5]
    projects = [d for d in detections if d["kind"] == "project" and d["confidence"] >= 0.5]
    mentions = [d for d in detections if d["kind"] in ("agent",)]

    return {
        "people": people,
        "projects": projects,
        "mentions": mentions,
        "total_detections": len(detections),
    }
