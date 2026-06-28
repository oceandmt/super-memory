from __future__ import annotations

import hashlib
from typing import Any


def make_source_event_key(metadata: dict[str, Any] | None, content_hash: str, *, source: str | None = None) -> str | None:
    meta = metadata or {}
    explicit = meta.get("idempotency_key") or meta.get("source_event_key")
    if explicit:
        return str(explicit)
    message_id = meta.get("message_id") or meta.get("event_id") or meta.get("source_event_id")
    if message_id:
        src = source or meta.get("source") or meta.get("source_adapter") or "openclaw"
        chat_id = meta.get("chat_id") or meta.get("conversation_label") or meta.get("channel") or ""
        sender_id = meta.get("sender_id") or meta.get("sender") or meta.get("username") or ""
        return hashlib.sha256(f"{src}:{chat_id}:{message_id}:{sender_id}:{content_hash}".encode()).hexdigest()
    return None
