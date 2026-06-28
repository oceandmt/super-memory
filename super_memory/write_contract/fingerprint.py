from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

_WORD_RE = re.compile(r"[\w\u0080-\uffff]+", re.UNICODE)

@dataclass(frozen=True)
class Fingerprint:
    raw_hash: str
    normalized_text: str
    normalized_hash: str
    simhash: int
    source_event_key: str | None = None


def normalize_for_dedup(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"```.*?```", " <code_block> ", text, flags=re.S)
    text = re.sub(r"`[^`]+`", " <inline_code> ", text)
    text = re.sub(r"https?://\S+", " <url> ", text)
    text = re.sub(r"\b[0-9a-f]{24,}\b", " <id> ", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2}[t\s][^\s]+", " <timestamp> ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _simhash(text: str, bits: int = 63) -> int:
    weights = [0] * bits
    tokens = _WORD_RE.findall(text)
    if not tokens:
        return 0
    for tok in tokens:
        h = int(hashlib.sha256(tok.encode("utf-8", errors="replace")).hexdigest(), 16)
        for i in range(bits):
            weights[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i, w in enumerate(weights):
        if w >= 0:
            out |= 1 << i
    return out


def build_fingerprint(content: str, source_event_key: str | None = None) -> Fingerprint:
    raw = content or ""
    norm = normalize_for_dedup(raw)
    return Fingerprint(
        raw_hash=hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest(),
        normalized_text=norm,
        normalized_hash=hashlib.sha256(norm.encode("utf-8", errors="replace")).hexdigest(),
        simhash=_simhash(norm),
        source_event_key=source_event_key,
    )


def hamming_distance(a: int, b: int) -> int:
    return int(a ^ b).bit_count()
