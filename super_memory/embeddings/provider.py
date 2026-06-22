"""Embedding provider abstraction with multi-backend support."""
from __future__ import annotations
import json, logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("super-memory.embeddings")

@dataclass
class EmbeddingResult:
    vector: list[float]
    provider: str
    dim: int
    model: str

class EmbeddingProvider:
    def __init__(self, name: str = "ollama", model: str = "nomic-embed-text", api_key: str | None = None):
        self.name = name
        self.model = model
        self.api_key = api_key
        self._dim = 768

    def embed(self, text: str) -> list[float]:
        if self.name == "ollama":
            return self._embed_ollama(text)
        elif self.name == "openai":
            return self._embed_openai(text)
        elif self.name == "gemini":
            return self._embed_gemini(text)
        elif self.name == "openrouter":
            return self._embed_openrouter(text)
        return self._embed_ollama(text)

    def similarity(self, a: list[float], b: list[float]) -> float:
        import math
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb + 1e-10) if na > 0 and nb > 0 else 0.0

    def _embed_ollama(self, text: str) -> list[float]:
        import urllib.request, json as _json
        payload = _json.dumps({"model": self.model, "prompt": text}).encode()
        try:
            req = urllib.request.Request("http://127.0.0.1:11434/api/embeddings", data=payload, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=30)
            data = _json.loads(resp.read())
            return data.get("embedding", [0.0] * self._dim)
        except Exception as e:
            logger.debug("ollama embed failed: %s", e)
            return [0.0] * self._dim

    def _embed_openai(self, text: str) -> list[float]:
        import urllib.request, json as _json
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        payload = _json.dumps({"model": self.model or "text-embedding-3-small", "input": text}).encode()
        try:
            req = urllib.request.Request("https://api.openai.com/v1/embeddings", data=payload, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
            data = _json.loads(resp.read())
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.debug("openai embed failed: %s", e)
            return [0.0] * self._dim

    def _embed_gemini(self, text: str) -> list[float]:
        import urllib.request, json as _json
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model or 'embedding-001'}:embedContent?key={self.api_key}"
        payload = _json.dumps({"model": f"models/{self.model or 'embedding-001'}", "content": {"parts": [{"text": text}]}}).encode()
        try:
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=30)
            data = _json.loads(resp.read())
            return data["embedding"]["values"]
        except Exception as e:
            logger.debug("gemini embed failed: %s", e)
            return [0.0] * self._dim

    def _embed_openrouter(self, text: str) -> list[float]:
        return self._embed_openai(text)  # OpenAI-compatible API


_providers: dict[str, EmbeddingProvider] = {}

def get_embedding_provider(name: str = "ollama", model: str = "nomic-embed-text", api_key: str | None = None) -> EmbeddingProvider:
    key = f"{name}:{model}"
    if key not in _providers:
        _providers[key] = EmbeddingProvider(name, model, api_key)
    return _providers[key]
