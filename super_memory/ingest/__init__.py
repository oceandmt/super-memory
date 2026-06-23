"""SourceAdapter Manifest — contract for memory source ingestion.

Borrowed from MemPalace BaseSourceAdapter (docs/rfcs/002-source-adapter-plugin-spec.md).

Each SourceAdapter declares:
1. What transformations it applies (chunking, summarization, extraction)
2. What privacy class it defaults to
3. What deterministic source IDs it generates
4. Version compatibility

This enables idempotent re-ingest, stale projection purge, and
source-aware quality/trust scoring.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Transformation Violation ─────────────────────────────────────────────────

class TransformationViolationError(RuntimeError):
    """Raised when a SourceAdapter violates its declared transformation."""
    pass


# ── Adapter Manifest ─────────────────────────────────────────────────────────

@dataclass
class SourceAdapterManifest:
    """Declared properties of a SourceAdapter.

    This is the contract: downstream code can trust that the adapter
    only applies these transformations and stays within these bounds.
    """
    name: str                              # e.g. "chat-turn", "file-markdown", "url-article"
    version: str                           # e.g. "1.2.0"
    declared_transformations: list[str]    # e.g. ["verbatim", "chunk", "extract-entities"]
    default_privacy_class: str             # e.g. "public", "session", "agent-local", "confidential"
    supports_structured: bool = False      # can emit structured fields (not just raw text)
    supported_extensions: list[str] = field(default_factory=list)
    max_content_bytes: int = 100_000       # safety limit
    requires_env: list[str] = field(default_factory=list)  # env vars needed


# ── Base SourceAdapter ───────────────────────────────────────────────────────

class BaseSourceAdapter(ABC):
    """Abstract base for memory source ingestion.

    Each subclass represents one source type (chat turn, file, URL, tool output).

    Key contract:
    - `can_handle(source_path: str) → bool`: return True if this adapter can ingest
    - `ingest(source_path: str, **kwargs) → list[dict]`: return memory payloads
    - `manifest() → SourceAdapterManifest`: declare capabilities
    """

    @abstractmethod
    def can_handle(self, source_path: str) -> bool:
        ...

    @abstractmethod
    def ingest(self, source_path: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Return list of memory payload dicts (ready for bridge.remember_batch)."""
        ...

    @classmethod
    @abstractmethod
    def manifest(cls) -> SourceAdapterManifest:
        ...

    @staticmethod
    def deterministic_source_id(content: str, adapter_name: str = "generic") -> str:
        """Generate a deterministic source ID from content.

        Key property: same content + adapter → same ID.
        Enables idempotent re-ingest and stale purge.
        """
        raw = f"{adapter_name}::{content}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    @staticmethod
    def normalize_source_path(source_path: str) -> str:
        """Normalize a source path for deterministic comparison."""
        return str(Path(source_path).resolve())


# ── Built-in Adapters ────────────────────────────────────────────────────────

class ChatTurnAdapter(BaseSourceAdapter):
    """Adapter for chat conversation turns."""

    @classmethod
    def manifest(cls) -> SourceAdapterManifest:
        return SourceAdapterManifest(
            name="chat-turn",
            version="1.0.0",
            declared_transformations=["verbatim"],
            default_privacy_class="session",
            supports_structured=True,
        )

    def can_handle(self, source_path: str) -> bool:
        return source_path.startswith("chat:") or source_path.startswith("turn:")

    def ingest(self, source_path: str, **kwargs: Any) -> list[dict[str, Any]]:
        content = kwargs.get("content", "")
        agent = kwargs.get("agent_id", "lucas")
        sid = self.deterministic_source_id(content, "chat-turn")
        return [{
            "id": sid,
            "content": content,
            "type": "context",
            "scope": "session",
            "agent_id": agent,
            "session_id": kwargs.get("session_id"),
            "project": kwargs.get("project"),
            "tags": ["source:chat", "adapter:chat-turn"],
            "source": "chat",
            "trust_score": 0.8,
            "metadata": {
                "source_adapter": "chat-turn",
                "source_id": sid,
                "transformations": ["verbatim"],
                "privacy_class": "session",
            },
        }]


class FileAdapter(BaseSourceAdapter):
    """Adapter for file content (markdown, code, docs)."""

    @classmethod
    def manifest(cls) -> SourceAdapterManifest:
        return SourceAdapterManifest(
            name="file",
            version="1.0.0",
            declared_transformations=["verbatim", "chunk"],
            default_privacy_class="project",
            supports_structured=False,
            supported_extensions=[".md", ".py", ".js", ".ts", ".json", ".yaml", ".txt", ".rst"],
            max_content_bytes=500_000,
        )

    def can_handle(self, source_path: str) -> bool:
        if source_path.startswith("file:"):
            source_path = source_path[5:]
        ext = Path(source_path).suffix.lower()
        return ext in self.manifest().supported_extensions or not source_path.startswith(("chat:", "turn:", "http", "tool:"))

    def ingest(self, source_path: str, **kwargs: Any) -> list[dict[str, Any]]:
        if source_path.startswith("file:"):
            source_path = source_path[5:]
        path = Path(source_path)
        if not path.exists():
            return []
        content = path.read_text(encoding="utf-8", errors="replace")
        sid = self.deterministic_source_id(content, "file")
        max_chars = self.manifest().max_content_bytes
        # Chunk if large
        if len(content) > max_chars:
            chunks = []
            for i in range(0, len(content), max_chars):
                chunk = content[i:i + max_chars]
                chunk_id = f"{sid}-chunk{i // max_chars}"
                chunks.append({
                    "id": chunk_id,
                    "content": chunk,
                    "type": "reference",
                    "scope": "project",
                    "agent_id": kwargs.get("agent_id", "lucas"),
                    "project": kwargs.get("project"),
                    "tags": ["source:file", "adapter:file", f"file:{path.name}"],
                    "source": str(path),
                    "trust_score": 0.9,
                    "metadata": {
                        "source_adapter": "file",
                        "source_id": sid,
                        "transformations": ["verbatim", "chunk"],
                        "chunk_index": i // max_chars,
                        "file": str(path),
                        "file_size": len(content),
                    },
                })
            return chunks
        return [{
            "id": sid,
            "content": content,
            "type": "reference",
            "scope": "project",
            "agent_id": kwargs.get("agent_id", "lucas"),
            "project": kwargs.get("project"),
            "tags": ["source:file", "adapter:file", f"file:{path.name}"],
            "source": str(path),
            "trust_score": 0.9,
            "metadata": {
                "source_adapter": "file",
                "source_id": sid,
                "transformations": ["verbatim"],
                "file": str(path),
                "file_size": len(content),
            },
        }]


class URLAdapter(BaseSourceAdapter):
    """Adapter for URL content."""

    @classmethod
    def manifest(cls) -> SourceAdapterManifest:
        return SourceAdapterManifest(
            name="url",
            version="1.0.0",
            declared_transformations=["extracted", "summarized"],
            default_privacy_class="public",
        )

    def can_handle(self, source_path: str) -> bool:
        return source_path.startswith("http://") or source_path.startswith("https://")

    def ingest(self, source_path: str, **kwargs: Any) -> list[dict[str, Any]]:
        content = kwargs.get("content", "")
        sid = self.deterministic_source_id(content or source_path, "url")
        return [{
            "id": sid,
            "content": content or source_path,
            "type": "reference",
            "scope": "project",
            "agent_id": kwargs.get("agent_id", "lucas"),
            "project": kwargs.get("project"),
            "tags": ["source:url", "adapter:url", f"url:{source_path[:80]}"] if not kwargs.get("tags") else kwargs["tags"],
            "source": source_path,
            "trust_score": 0.6,
            "metadata": {
                "source_adapter": "url",
                "source_id": sid,
                "transformations": ["extracted"],
                "url": source_path,
            },
        }]


# ── Adapter Registry ─────────────────────────────────────────────────────────

_ADAPTERS: dict[str, type[BaseSourceAdapter]] = {}


def register_adapter(name: str, adapter_cls: type[BaseSourceAdapter]) -> None:
    _ADAPTERS[name] = adapter_cls


def get_adapter(name: str) -> type[BaseSourceAdapter] | None:
    return _ADAPTERS.get(name)


def list_adapters() -> dict[str, SourceAdapterManifest]:
    return {name: cls.manifest() for name, cls in _ADAPTERS.items()}


def resolve_adapter(source_path: str) -> BaseSourceAdapter | None:
    """Auto-detect adapter for a source path."""
    for cls in _ADAPTERS.values():
        instance = cls()
        if instance.can_handle(source_path):
            return instance
    return None


def ingest_through_adapter(source_path: str, **kwargs: Any) -> list[dict[str, Any]]:
    """Ingest a source through the best matching adapter."""
    adapter = resolve_adapter(source_path)
    if adapter is None:
        # Fallback: file adapter
        adapter = FileAdapter()
    return adapter.ingest(source_path, **kwargs)


# Register built-in adapters
register_adapter("chat-turn", ChatTurnAdapter)
register_adapter("file", FileAdapter)
register_adapter("url", URLAdapter)
