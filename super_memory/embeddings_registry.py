"""Embedding provider registry and adapter framework.

Matches OpenClaw memory-core provider-adapters pattern:
- Abstract base for embedding providers
- Auto-detection and fallback chain
- 7 built-in providers: sqlite_vec, sentence_transformers, openai, text2vec, voyage, cohere, huggingface
- Priority-ordered selection
"""

from __future__ import annotations

import abc
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── Provider priority (lower = tried first) ────────────────────────────────

PROVIDER_PRIORITY: dict[str, int] = {
    "sqlite_vec": 0,            # Local, no external deps
    "sentence_transformers": 1, # Local, needs torch
    "text2vec": 2,              # Local, needs torch
    "openai": 3,                # API key required
    "voyage": 4,                # API key required
    "cohere": 5,                # API key required
    "huggingface": 6,           # API key optional
}


# ── Abstract adapter ───────────────────────────────────────────────────────


class EmbeddingAdapter(abc.ABC):
    """Base class for embedding providers."""

    name: str = "base"

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is usable (deps, keys, etc.)."""
        ...

    @abc.abstractmethod
    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        """Embed a single text string into a vector."""
        ...

    @abc.abstractmethod
    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        """Embed a batch of texts into vectors (more efficient for multiple)."""
        ...

    def health(self) -> dict[str, Any]:
        """Return health check info."""
        return {"name": self.name, "available": self.is_available()}


# ── Adapter implementations ────────────────────────────────────────────────


class SQLiteVecAdapter(EmbeddingAdapter):
    """sqlite_vec — AllMiniLML6 v2 via local ONNX/SQLite extension."""

    name = "sqlite_vec"

    def is_available(self) -> bool:
        try:
            import sqlite_vec  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        dim = dimensions or 384
        try:
            from sqlite_vec.experimental import vector_from_text
            return vector_from_text(text, dim)
        except Exception:
            raise RuntimeError(f"{self.name}: embed failed")

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        return [self.embed(t, dimensions=dimensions) for t in texts]


class SentenceTransformersAdapter(EmbeddingAdapter):
    """sentence-transformers — Local transformer models."""

    name = "sentence_transformers"
    _model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            SentenceTransformersAdapter._model = SentenceTransformer("all-MiniLM-L6-v2")
        return SentenceTransformersAdapter._model

    def is_available(self) -> bool:
        try:
            import sentence_transformers  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        model = self._get_model()
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()[:dimensions] if dimensions else vec.tolist()

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        model = self._get_model()
        vecs = model.encode(texts, normalize_embeddings=True)
        return [v.tolist()[:dimensions] if dimensions else v.tolist() for v in vecs]


class OpenAIAdapter(EmbeddingAdapter):
    """OpenAI embeddings API."""

    name = "openai"
    _client = None

    def _get_client(self):
        if self._client is None:
            import openai
            OpenAIAdapter._client = openai.OpenAI()
        return OpenAIAdapter._client

    def is_available(self) -> bool:
        try:
            import openai  # noqa: F401
            return bool(self._get_client().api_key)
        except Exception:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        client = self._get_client()
        model = "text-embedding-3-small"
        kwargs = {"dimensions": dimensions} if dimensions and dimensions <= 1536 else {}
        resp = client.embeddings.create(model=model, input=text, **kwargs)
        return resp.data[0].embedding

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        client = self._get_client()
        model = "text-embedding-3-small"
        kwargs = {"dimensions": dimensions} if dimensions and dimensions <= 1536 else {}
        resp = client.embeddings.create(model=model, input=texts, **kwargs)
        return [d.embedding for d in resp.data]


class Text2VecAdapter(EmbeddingAdapter):
    """text2vec — Lightweight local Chinese-capable embeddings."""

    name = "text2vec"
    _model = None

    def _get_model(self):
        if self._model is None:
            from text2vec import SentenceModel
            Text2VecAdapter._model = SentenceModel("shibing624/text2vec-base-chinese")
        return Text2VecAdapter._model

    def is_available(self) -> bool:
        try:
            import text2vec  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        model = self._get_model()
        vec = model.encode(text)
        return vec.tolist()[:dimensions] if dimensions else vec.tolist()

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        return [self.embed(t, dimensions=dimensions) for t in texts]


class VoyageAdapter(EmbeddingAdapter):
    """Voyage AI embeddings API."""

    name = "voyage"
    _client = None

    def _get_client(self):
        if self._client is None:
            import voyageai
            VoyageAdapter._client = voyageai.Client()
        return VoyageAdapter._client

    def is_available(self) -> bool:
        try:
            import voyageai  # noqa: F401
            client = self._get_client()
            return bool(client.api_key)
        except Exception:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        client = self._get_client()
        resp = client.embed(text, model="voyage-3", input_type="document")
        return resp.embeddings[0][:dimensions] if dimensions else resp.embeddings[0]

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        client = self._get_client()
        resp = client.embed(texts, model="voyage-3", input_type="document")
        return [e[:dimensions] if dimensions else e for e in resp.embeddings]


class CohereAdapter(EmbeddingAdapter):
    """Cohere embeddings API."""

    name = "cohere"
    _client = None

    def _get_client(self):
        if self._client is None:
            import cohere
            CohereAdapter._client = cohere.Client()
        return CohereAdapter._client

    def is_available(self) -> bool:
        try:
            import cohere  # noqa: F401
            client = self._get_client()
            return bool(client.api_key)
        except Exception:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        client = self._get_client()
        resp = client.embed(texts=[text], model="embed-english-v3.0", input_type="search_document")
        return resp.embeddings[0][:dimensions] if dimensions else resp.embeddings[0]

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        client = self._get_client()
        resp = client.embed(texts=texts, model="embed-english-v3.0", input_type="search_document")
        return [e[:dimensions] if dimensions else e for e in resp.embeddings]


class HuggingFaceAdapter(EmbeddingAdapter):
    """HuggingFace Inference API embeddings."""

    name = "huggingface"
    _client = None

    def _get_client(self):
        if self._client is None:
            from huggingface_hub import InferenceClient
            HuggingFaceAdapter._client = InferenceClient()
        return HuggingFaceAdapter._client

    def is_available(self) -> bool:
        try:
            from huggingface_hub import InferenceClient  # noqa: F401
            return True
        except ImportError:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        client = self._get_client()
        vec = client.feature_extraction(text, model="sentence-transformers/all-MiniLM-L6-v2")
        # HuggingFace returns list of lists; take first or mean pool
        if vec and isinstance(vec[0], (list, tuple)):
            import numpy as np
            vec = np.mean(vec, axis=0).tolist()
        return vec[:dimensions] if dimensions else vec

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        return [self.embed(t, dimensions=dimensions) for t in texts]


# ── Registry ───────────────────────────────────────────────────────────────


BUILTIN_ADAPTERS: list[EmbeddingAdapter] = [
    SQLiteVecAdapter(),
    SentenceTransformersAdapter(),
    Text2VecAdapter(),
    OpenAIAdapter(),
    VoyageAdapter(),
    CohereAdapter(),
    HuggingFaceAdapter(),
]


def get_available_adapters() -> list[EmbeddingAdapter]:
    """Return all adapters, ordered by priority (lower first)."""
    return sorted(BUILTIN_ADAPTERS, key=lambda a: PROVIDER_PRIORITY.get(a.name, 99))


def select_best_adapter() -> EmbeddingAdapter | None:
    """Auto-select the best available embedding provider."""
    for adapter in get_available_adapters():
        if adapter.is_available():
            logger.info(f"embedding_registry: selected adapter={adapter.name}")
            return adapter
    logger.warning("embedding_registry: no embedding provider available")
    return None


def embed_with_best(text: str, *, dimensions: int | None = None) -> list[float] | None:
    """Embed text using the best available provider."""
    adapter = select_best_adapter()
    if adapter is None:
        return None
    return adapter.embed(text, dimensions=dimensions)


def list_providers() -> list[dict[str, Any]]:
    """List all providers with availability status."""
    return [
        {"name": a.name, "available": a.is_available(), "priority": PROVIDER_PRIORITY.get(a.name, 99)}
        for a in BUILTIN_ADAPTERS
    ]
