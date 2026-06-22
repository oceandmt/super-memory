"""Entity extraction for Super Memory — ported concepts from neural-memory.

Extracts named entities, code symbols, financial metrics, temporal refs,
and domain-specific terms from memory content on save. Stores in metadata
for better recall precision.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("super-memory.entity_extractor")


# ── Entity Types ──────────────────────────────────────────────────────────────
ENTITY_TYPES = {
    "person": "person",
    "location": "location",
    "organization": "organization",
    "product": "product",
    "event_name": "event_name",
    "code_symbol": "code_symbol",
    "api_endpoint": "api_endpoint",
    "error_type": "error_type",
    "version": "version",
    "financial_metric": "financial_metric",
    "currency_amount": "currency_amount",
    "regulation": "regulation",
    "package_name": "package_name",
    "module_name": "module_name",
    "function_name": "function_name",
    "class_name": "class_name",
}


@dataclass
class ExtractedEntity:
    text: str
    type: str
    start: int
    end: int
    confidence: float = 1.0


# ── Regex Patterns ────────────────────────────────────────────────────────────

# Email (low confidence to avoid over-capture)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# URL
_URL_RE = re.compile(r"https?://[^\s<>\"']+|ftp://[^\s<>\"']+")

# Python class names (CamelCase starting uppercase)
_CLASS_RE = re.compile(r"\b([A-Z][a-zA-Z0-9]+(?:Error|Exception|Handler|Manager|Service|Store|Config|Client|Provider|Factory|Builder|Adapter|Repository))\b")

# Python function names (snake_case, lower start)
_FUNC_RE = re.compile(r"\b([a-z_][a-zA-Z0-9_]+(?:_[a-z0-9_]+)*)\s*\(")

# Module/package paths
_MODULE_RE = re.compile(r"\b([a-z_][a-zA-Z0-9_]*\.[a-z_][a-zA-Z0-9_.]*)\b")

# Version strings (semver x.y.z OR x.y)
_VERSION_RE = re.compile(r"\b(v?\d+\.\d+(?:\.\d+)?(?:[-.]\w+(?:\.\d+)?)?)\b")

# API endpoints (with or without HTTP method prefix)
_API_RE = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(/[a-zA-Z0-9_/{}]+\b)")
# API paths (bare, no method prefix)
_BARE_API_RE = re.compile(r"(?:\b|(?<=\s))(/api(?:/v\d+)?/[a-zA-Z0-9_/{}.-]+)\b")

# Currency amounts ($25M, 500 triệu VND, 1.5 tỷ)
_CURRENCY_RE = re.compile(r"\b(\$[\d,.]+[MBK]?|[\d,.]+(?: triệu| tỷ| nghìn)\s*(?:VND|USD|EUR)?)\b")

# Financial metrics (ROE, EBITDA, P/E, CAGR...)
_FINANCIAL_RE = re.compile(r"\b(ROE|ROA|EBITDA|EBIT|P/E|P/B|CAGR|EPS|ROIC|IRR|NPV|DCF|FCF|WACC|CAPM|COGS|SG&A)\b")

# Python error types
_ERROR_RE = re.compile(r"\b([A-Z][a-zA-Z]+Error|ValueError|TypeError|KeyError|IndexError|AttributeError|ImportError|ModuleNotFoundError|RuntimeError|OSError|IOError|ConnectionError|TimeoutError|PermissionError|FileNotFoundError|SyntaxError|IndentationError|NameError|StopIteration|RecursionError|AssertionError)\b")

# Package names (common registries)
_PACKAGE_RE = re.compile(r"\b(numpy|pandas|torch|tensorflow|jax|scipy|scikit-learn|flask|fastapi|django|aiohttp|requests|httpx|sqlalchemy|alembic|pydantic|typer|rich|click|loguru|structlog|pytest|ruff|black|mypy|celery|redis|kafka|pyspark|ray|dask|numba|cupy|transformers|langchain|llama-index|chromadb|qdrant-client|weaviate|pinecone\b)")

# Vietnamese person name prefixes + 2-3 word names
_VI_NAME_RE = re.compile(r"\b(Anh|Chị|Em|Bạn|Cô|Chú|Bác|Ông|Bà|Thầy)\s+([AÀẢÃÁẠĂẰẲẴẮẶÂẦẨẪẤẬBCDĐEÈẺẼÉẸÊỀỂỄẾỆFGHIÌỈĨÍỊJKLMNOÒỎÕÓỌÔỒỔỖỐỘƠỜỞỠỚỢPQRSTUÙỦŨÚỤƯỪỬỮỨỰVXYÝỲỶỸỴZ][aàảãáạăằẳẵắặâầẩẫấậbcdđeèẻẽéẹêềểễếệfghiìỉĩíịjklmnoòỏõóọôồổỗốộơờởỡớợpqrstuùủũúụưừửữứựvxyýỳỷỹỵz]+)\b")

# Fallback: capitalized 2-word names (common English/Vietnamese names)
_CAPITALIZED_NAME_RE = re.compile(r"\b([A-Z][a-z]+\s[A-Z][a-z]+)\b")

# Common tech/tool names (language, framework, OS, tool) — case insensitive
_TECH_NAME_RE = re.compile(r"\b(Python|JavaScript|TypeScript|Java|Go|Rust|C\+\+|C#|Ruby|PHP|Kotlin|Swift|Scala|Elixir|Haskell|Clojure|Dart|Lua|Perl\b|R\b|MATLAB|Bash|PowerShell|Node\.js|Deno|Bun|React|Vue\.js|Angular|Svelte|Next\.js|Nuxt|Django|Flask|FastAPI|Spring|Rails|Laravel|Symfony|Express|Keras|PyTorch|TensorFlow|JAX|Docker|Kubernetes|Helm|Terraform|Ansible|Nginx|Apache|Redis|PostgreSQL|MySQL|MongoDB|SQLite|Elasticsearch|Kafka|RabbitMQ|Celery|GitHub\s?Actions|GitLab\s?CI|Jenkins|CircleCI|Grafana|Prometheus|Datadog|New\s?Relic|AWS|Azure|GCP|Linux|Ubuntu|Debian|CentOS|Alpine|macOS|Windows|Android|iOS|CUDA|OpenCL|WebAssembly|GraphQL|REST|gRPC|WebSocket|OAuth|JWT|SSL|TLS|HTTP|HTTPS|JSON|YAML|XML|CSV|Parquet|Avro|Arrow|Protocol\s?Buffers)\b", re.IGNORECASE)


# ── Main Extractor ────────────────────────────────────────────────────────────

class EntityExtractor:
    """Extract entities from memory content for better recall."""

    def __init__(self) -> None:
        self._patterns: list[tuple[str, re.Pattern, float]] = [
            ("email", _EMAIL_RE, 0.6),
            ("url", _URL_RE, 0.9),
            ("error_type", _ERROR_RE, 0.95),
            ("class_name", _CLASS_RE, 0.85),
            ("financial_metric", _FINANCIAL_RE, 0.95),
            ("currency_amount", _CURRENCY_RE, 0.9),
            ("version", _VERSION_RE, 0.85),
            ("api_endpoint", _API_RE, 0.9),
            ("api_endpoint", _BARE_API_RE, 0.75),
            ("package_name", _PACKAGE_RE, 0.85),
            ("module_name", _MODULE_RE, 0.7),
        ]
        # Function names need a 2-pass dedup check (remove after module names)
        self._func_pattern = ("function_name", _FUNC_RE, 0.75)
        # Vietnamese names
        self._vi_pattern = ("person", _VI_NAME_RE, 0.6)
        # Capitalized 2-word names (lower confidence)
        self._cap_pattern = ("person", _CAPITALIZED_NAME_RE, 0.35)
        # Tech/tool names
        self._tech_pattern = ("product", _TECH_NAME_RE, 0.8)

    def extract(self, text: str) -> list[ExtractedEntity]:
        """Extract entities from text. Returns deduplicated sorted list."""
        if not text or len(text) < 10:
            return []

        entities: list[ExtractedEntity] = []
        seen: set[tuple[str, str]] = set()  # (type, text_lower)
        text_lower = text.lower()

        # Run regex patterns
        for etype, pattern, conf in self._patterns:
            for match in pattern.finditer(text):
                key = (etype, match.group(0).lower())
                if key not in seen:
                    seen.add(key)
                    entities.append(ExtractedEntity(
                        text=match.group(0),
                        type=etype,
                        start=match.start(),
                        end=match.end(),
                        confidence=conf,
                    ))

        # Function names (skip if already matched as module)
        module_texts = set(e.text.lower() for e in entities if e.type == "module_name")
        for match in self._func_pattern[1].finditer(text):
            name = match.group(1)
            key = ("function_name", name.lower())
            if key not in seen and name.lower() not in module_texts:
                seen.add(key)
                entities.append(ExtractedEntity(
                    text=name,
                    type="function_name",
                    start=match.start(),
                    end=match.end(),
                    confidence=self._func_pattern[2],
                ))

        # Vietnamese person names
        for match in self._vi_pattern[1].finditer(text):
            full_name = match.group(0)
            key = ("person", full_name.lower())
            if key not in seen:
                seen.add(key)
                entities.append(ExtractedEntity(
                    text=full_name,
                    type="person",
                    start=match.start(),
                    end=match.end(),
                    confidence=self._vi_pattern[2],
                ))

        # Tech/tool names (language, framework, OS, tool)
        for match in self._tech_pattern[1].finditer(text):
            name = match.group(0)
            key = ("product", name.lower())
            if key not in seen:
                seen.add(key)
                entities.append(ExtractedEntity(
                    text=name,
                    type="product",
                    start=match.start(),
                    end=match.end(),
                    confidence=self._tech_pattern[2],
                ))

        # Fallback capitalized names (only for longer text with context)
        if len(text) > 200:
            for match in self._cap_pattern[1].finditer(text):
                full_name = match.group(1)
                # Skip if matches common false positives
                if full_name.lower() in {
                    "hello world", "the user", "this is", "there is", "that was",
                    "note that", "make sure", "the code", "the api", "the file",
                    "import os", "import sys", "the end", "from the", "the new",
                    "the same", "the best", "the most", "the first", "the last",
                    "the only", "the main", "the next", "the current",
                }:
                    continue
                key = ("person", full_name.lower())
                if key not in seen:
                    seen.add(key)
                    entities.append(ExtractedEntity(
                        text=full_name,
                        type="person",
                        start=match.start(),
                        end=match.end(),
                        confidence=self._cap_pattern[2],
                    ))

        # Sort by position
        entities.sort(key=lambda e: e.start)
        return entities

    def extract_to_metadata(self, text: str) -> dict[str, Any]:
        """Extract entities and return as serializable metadata dict."""
        entities = self.extract(text)
        if not entities:
            return {}

        by_type: dict[str, list[str]] = {}
        for e in entities:
            by_type.setdefault(e.type, []).append(e.text)

        return {
            "entities": by_type,
            "entity_count": len(entities),
            "entity_types": list(by_type.keys()),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_extractor: EntityExtractor | None = None


def get_extractor() -> EntityExtractor:
    global _extractor
    if _extractor is None:
        _extractor = EntityExtractor()
    return _extractor


def extract_entities(text: str) -> list[ExtractedEntity]:
    """Convenience: extract entities from text."""
    return get_extractor().extract(text)


def extract_metadata(text: str) -> dict[str, Any]:
    """Convenience: extract entities as metadata dict."""
    return get_extractor().extract_to_metadata(text)
