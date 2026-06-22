"""Multi-provider embeddings — OpenAI, Gemini, OpenRouter, Ollama."""
from .provider import get_embedding_provider, EmbeddingProvider, EmbeddingResult

__all__ = ["get_embedding_provider", "EmbeddingProvider", "EmbeddingResult"]
