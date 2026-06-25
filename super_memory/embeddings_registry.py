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
import os
from typing import Any

logger = logging.getLogger(__name__)


# ── Provider priority (lower = tried first) ────────────────────────────────

PROVIDER_PRIORITY: dict[str, int] = {
    "sqlite_vec": 0,            # Local, no external deps
    "sentence_transformers": 1, # Local, needs torch
    "text2vec": 2,              # Local, needs torch
    "lm_studio": 3,             # Local, LM Studio running
    "openai": 4,                # API key required
    "mistral": 5,               # API key required
    "voyage": 6,                # API key required
    "cohere": 7,                # API key required
    "deepinfra": 8,             # API key required
    "google": 9,                # API key required
    "huggingface": 10,          # API key optional
    "bedrock": 11,              # AWS creds required
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
            # sqlite-vec 0.1.x exposes vector storage/search but not text embedding.
            # Provide a deterministic local lexical hash fallback so REM can be
            # initialized without external APIs. This is not semantic embedding, but
            # it gives stable approximate lexical vectors until a real provider
            # (sentence_transformers/openai/etc.) is configured.
            import hashlib
            import math
            import re
            vec = [0.0] * dim
            tokens = re.findall(r"[\w\u0080-\uffff]+", str(text).lower())
            if not tokens:
                return vec
            for tok in tokens:
                h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(h[:4], "little") % dim
                sign = -1.0 if (h[4] & 1) else 1.0
                vec[idx] += sign
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            return [v / norm for v in vec]

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


class MistralAdapter(EmbeddingAdapter):
    """Mistral AI embeddings API."""

    name = "mistral"
    _client = None

    def _get_client(self):
        if self._client is None:
            from mistralai import MistralAI
            MistralAdapter._client = MistralAI()
        return MistralAdapter._client

    def is_available(self) -> bool:
        try:
            from mistralai import MistralAI  # noqa: F401
            return bool(os.environ.get("MISTRAL_API_KEY"))
        except ImportError:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        client = self._get_client()
        model = "mistral-embed"
        resp = client.embeddings.create(model=model, inputs=[text])
        return resp.data[0].embedding[:dimensions] if dimensions else resp.data[0].embedding

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        client = self._get_client()
        model = "mistral-embed"
        resp = client.embeddings.create(model=model, inputs=texts)
        return [e[:dimensions] if dimensions else e for e in resp.data]


class BedrockAdapter(EmbeddingAdapter):
    """Amazon Bedrock embeddings (Cohere embed on Bedrock)."""

    name = "bedrock"
    _client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            BedrockAdapter._client = boto3.client("bedrock-runtime")
        return BedrockAdapter._client

    def is_available(self) -> bool:
        try:
            import boto3  # noqa: F401
            return True
        except ImportError:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        import json as _json
        client = self._get_client()
        body = _json.dumps({"input_text": text, "input_type": "search_document"})
        resp = client.invoke_model(
            body=body,
            modelId="cohere.embed-english-v3",
            accept="application/json",
            contentType="application/json",
        )
        result = _json.loads(resp["body"].read())
        embeddings = result.get("embeddings", [[]])
        vec = embeddings[0] if embeddings else []
        return vec[:dimensions] if dimensions else vec

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        return [self.embed(t, dimensions=dimensions) for t in texts]


class LMStudioAdapter(EmbeddingAdapter):
    """LM Studio local embeddings (OpenAI-compatible API)."""

    name = "lm_studio"
    _client = None

    def _get_client(self):
        if self._client is None:
            import openai
            LMStudioAdapter._client = openai.OpenAI(
                base_url="http://localhost:1234/v1",
                api_key="not-needed",
            )
        return LMStudioAdapter._client

    def is_available(self) -> bool:
        try:
            import openai  # noqa: F401
            client = self._get_client()
            resp = client.models.list()
            return bool(resp.data)
        except Exception:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        client = self._get_client()
        resp = client.embeddings.create(model="local-model", input=text)
        return resp.data[0].embedding[:dimensions] if dimensions else resp.data[0].embedding

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        client = self._get_client()
        resp = client.embeddings.create(model="local-model", input=texts)
        return [d.embedding[:dimensions] if dimensions else d.embedding for d in resp.data]


class DeepInfraAdapter(EmbeddingAdapter):
    """DeepInfra embeddings API."""

    name = "deepinfra"
    _client = None

    def _get_client(self):
        if self._client is None:
            import openai
            DeepInfraAdapter._client = openai.OpenAI(
                base_url="https://api.deepinfra.com/v1/openai",
                api_key=os.environ.get("DEEPINFRA_API_KEY", ""),
            )
        return DeepInfraAdapter._client

    def is_available(self) -> bool:
        try:
            import openai  # noqa: F401
            return bool(os.environ.get("DEEPINFRA_API_KEY"))
        except ImportError:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        client = self._get_client()
        model = "BAAI/bge-large-en-v1.5"
        resp = client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding[:dimensions] if dimensions else resp.data[0].embedding

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        client = self._get_client()
        model = "BAAI/bge-large-en-v1.5"
        resp = client.embeddings.create(model=model, input=texts)
        return [d.embedding[:dimensions] if dimensions else d.embedding for d in resp.data]


class GoogleAdapter(EmbeddingAdapter):
    """Google Vertex AI / Generative AI embeddings."""

    name = "google"
    _client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            GoogleAdapter._client = genai.Client()
        return GoogleAdapter._client

    def is_available(self) -> bool:
        try:
            from google import genai  # noqa: F401
            return bool(os.environ.get("GOOGLE_API_KEY"))
        except ImportError:
            return False

    def embed(self, text: str, *, dimensions: int | None = None) -> list[float]:
        client = self._get_client()
        resp = client.models.embed_content(
            model="models/text-embedding-004",
            contents=text,
        )
        vec = resp.embeddings[0].values
        return vec[:dimensions] if dimensions else vec

    def embed_batch(self, texts: list[str], *, dimensions: int | None = None) -> list[list[float]]:
        return [self.embed(t, dimensions=dimensions) for t in texts]


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
    LMStudioAdapter(),
    OpenAIAdapter(),
    MistralAdapter(),
    VoyageAdapter(),
    CohereAdapter(),
    DeepInfraAdapter(),
    GoogleAdapter(),
    HuggingFaceAdapter(),
    BedrockAdapter(),
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


# ── Dynamic Provider Registry (Micro-gap 2) ───────────────────────────

# Mirrors memory-core provider-adapter-registration.ts:
# - filterUnregisteredMemoryEmbeddingProviderAdapters()
# - dynamic add/remove/reorder

_registered_adapter_ids: set[str] = set()


def register_provider(adapter: EmbeddingAdapter) -> dict[str, Any]:
    """Dynamically register a new provider adapter.

    Args:
        adapter: EmbeddingAdapter instance to register.

    Returns:
        Dict with ok, name, priority status.
    """
    name = adapter.name
    if name not in PROVIDER_PRIORITY:
        # Auto-assign next priority after max
        max_prio = max(PROVIDER_PRIORITY.values()) if PROVIDER_PRIORITY else 0
        PROVIDER_PRIORITY[name] = max_prio + 1

    # Add to builtin list if not already there
    existing_names = {a.name for a in BUILTIN_ADAPTERS}
    if name not in existing_names:
        BUILTIN_ADAPTERS.append(adapter)

    _registered_adapter_ids.add(name)
    return {
        "ok": True,
        "name": name,
        "priority": PROVIDER_PRIORITY.get(name, 99),
        "already_registered": name in existing_names,
    }


def unregister_provider(name: str) -> dict[str, Any]:
    """Dynamically unregister a provider adapter.

    Args:
        name: Provider name to remove.

    Returns:
        Dict with ok and name.
    """
    global BUILTIN_ADAPTERS
    _registered_adapter_ids.discard(name)
    BUILTIN_ADAPTERS = [a for a in BUILTIN_ADAPTERS if a.name != name]
    PROVIDER_PRIORITY.pop(name, None)
    return {"ok": True, "name": name}


def filter_unregistered_adapters(builtin_names: list[str] | None = None) -> list[str]:
    """Filter which builtin adapters have NOT been registered yet.

    Mirrors memory-core `filterUnregisteredMemoryEmbeddingProviderAdapters()`.
    Returns list of provider names from builtins that are not yet in registered set.

    Args:
        builtin_names: Optional subset to check. Defaults to all BUILTIN_ADAPTERS names.

    Returns:
        List of provider names that are unregistered.
    """
    check_names = builtin_names or [a.name for a in BUILTIN_ADAPTERS]
    return [n for n in check_names if n not in _registered_adapter_ids]


def list_providers(include_unregistered: bool = True) -> list[dict[str, Any]]:
    """List all providers with availability and registration status.

    Args:
        include_unregistered: If True, include all builtins.
            If False, only returns dynamically registered providers.

    Returns:
        List of provider info dicts.
    """
    adapters = BUILTIN_ADAPTERS if include_unregistered else [
        a for a in BUILTIN_ADAPTERS if a.name in _registered_adapter_ids
    ]
    return [
        {
            "name": a.name,
            "available": a.is_available(),
            "priority": PROVIDER_PRIORITY.get(a.name, 99),
            "registered": a.name in _registered_adapter_ids,
        }
        for a in adapters
    ]


def get_registry_stats() -> dict[str, Any]:
    """Get provider registry statistics."""
    all_providers = list_providers(include_unregistered=True)
    registered = [p for p in all_providers if p["registered"]]
    available = [p for p in all_providers if p["available"]]
    return {
        "total": len(all_providers),
        "registered": len(registered),
        "unregistered": len(all_providers) - len(registered),
        "available": len(available),
        "registered_names": [p["name"] for p in registered],
        "available_names": [p["name"] for p in available],
    }
