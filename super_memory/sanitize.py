from __future__ import annotations

import re
from typing import Any

from .models import MemoryScope, MemoryType

_MAX_PROMPT_CHARS = 8000
_MAX_MEMORY_CHARS = 4000
_ALLOWED_MEMORY_KEYS = {
    "content",
    "type",
    "scope",
    "agent_id",
    "session_id",
    "project",
    "tags",
    "source",
    "trust_score",
    "metadata",
}
_KEY_ALIASES = {
    "agentId": "agent_id",
    "agent": "agent_id",
    "sessionId": "session_id",
    "session": "session_id",
    "trustScore": "trust_score",
    "trust": "trust_score",
    "memoryType": "type",
    "memory_type": "type",
    "memoryScope": "scope",
    "memory_scope": "scope",
}
_TYPE_ALIASES = {
    "decision-memory": "decision",
    "instruction": "doctrine",
    "error": "blocker",
    "reference": "context",
    "task": "todo",
}
_SCOPE_ALIASES = {
    "agent_local": "agent-local",
    "agent": "agent-local",
    "local": "agent-local",
    "cross_agent": "cross-agent",
    "global": "shared",
}
_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|authorization)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS = re.compile(r"[ \t]+")

def sanitize_prompt(text: Any, *, max_chars: int = _MAX_PROMPT_CHARS) -> str:
    """Sanitize recall/prompt text without changing user-visible meaning.

    This removes control characters, redacts common secret shapes, normalizes line
    whitespace, and caps length. It is intentionally deterministic and local.
    """

    if text is None:
        return ""
    out = str(text)
    out = _CONTROL_CHARS.sub("", out).replace("\r\n", "\n").replace("\r", "\n")
    out = "\n".join(_WS.sub(" ", line).strip() for line in out.split("\n"))
    out = "\n".join(line for line in out.split("\n") if line)
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(lambda m: f"{m.group(1)}=[REDACTED]" if m.lastindex and m.lastindex >= 1 else "[REDACTED]", out)
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    return out


def sanitize_auto_capture(text: Any, *, max_chars: int = _MAX_MEMORY_CHARS) -> str:
    """Sanitize text before it can become a stored auto-capture memory."""

    return sanitize_prompt(text, max_chars=max_chars)


def normalize_memory_payload(payload: dict[str, Any], *, auto_capture: bool = False) -> dict[str, Any]:
    """Normalize external memory schemas into Super Memory's canonical payload.

    The returned dict contains only supported keys. Aliases are folded into snake
    case, enum-like values are canonicalized, tags are deduped strings, metadata
    is guaranteed to be a dict, and content is sanitized. Unknown top-level keys
    are moved to metadata.dropped_fields for auditability instead of being saved
    as first-class schema.
    """

    normalized: dict[str, Any] = {}
    dropped: dict[str, Any] = {}
    for key, value in dict(payload).items():
        canonical_key = _KEY_ALIASES.get(key, key)
        if canonical_key in _ALLOWED_MEMORY_KEYS:
            normalized[canonical_key] = value
        else:
            dropped[key] = value

    content = normalized.get("content", "")
    normalized["content"] = sanitize_auto_capture(content) if auto_capture else sanitize_prompt(content, max_chars=_MAX_MEMORY_CHARS)
    normalized["type"] = _normalize_enum(normalized.get("type"), MemoryType, MemoryType.CONTEXT.value, _TYPE_ALIASES)
    normalized["scope"] = _normalize_enum(normalized.get("scope"), MemoryScope, MemoryScope.SESSION.value, _SCOPE_ALIASES)
    normalized["agent_id"] = sanitize_prompt(normalized.get("agent_id") or "lucas", max_chars=80) or "lucas"

    for key in ["session_id", "project", "source"]:
        if normalized.get(key) is not None:
            normalized[key] = sanitize_prompt(normalized[key], max_chars=200)

    normalized["tags"] = _normalize_tags(normalized.get("tags", []))
    normalized["metadata"] = _normalize_metadata(normalized.get("metadata"))
    if dropped:
        normalized["metadata"].setdefault("dropped_fields", sorted(dropped.keys()))
    if "trust_score" in normalized and normalized["trust_score"] is not None:
        try:
            normalized["trust_score"] = max(0.0, min(1.0, float(normalized["trust_score"])))
        except (TypeError, ValueError):
            normalized["trust_score"] = None
    return normalized


def normalize_memory_batch(payloads: list[dict[str, Any]], *, auto_capture: bool = False, max_items: int = 20) -> list[dict[str, Any]]:
    return [normalize_memory_payload(item, auto_capture=auto_capture) for item in payloads[:max_items]]


def _normalize_enum(value: Any, enum_cls: Any, default: str, aliases: dict[str, str]) -> str:
    if value is None:
        return default
    if hasattr(value, "value"):
        value = value.value
    raw = str(value).strip().lower().replace("_", "-")
    raw = aliases.get(raw, raw)
    allowed = {item.value for item in enum_cls}
    return raw if raw in allowed else default


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        values: list[Any] = []
    elif isinstance(value, str):
        values = re.split(r"[,\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    seen: set[str] = set()
    out: list[str] = []
    for tag in values:
        clean = sanitize_prompt(tag, max_chars=100).strip().lower().replace(" ", "-")
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _normalize_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key, item in value.items():
        clean_key = sanitize_prompt(key, max_chars=80)
        if not clean_key:
            continue
        if isinstance(item, str):
            out[clean_key] = sanitize_prompt(item, max_chars=1000)
        elif isinstance(item, (int, float, bool)) or item is None:
            out[clean_key] = item
        elif isinstance(item, (list, tuple, set)):
            out[clean_key] = [sanitize_prompt(v, max_chars=500) if isinstance(v, str) else v for v in list(item)[:50]]
        elif isinstance(item, dict):
            out[clean_key] = {sanitize_prompt(k, max_chars=80): sanitize_prompt(v, max_chars=500) if isinstance(v, str) else v for k, v in item.items()}
        else:
            out[clean_key] = sanitize_prompt(item, max_chars=500)
    return out
