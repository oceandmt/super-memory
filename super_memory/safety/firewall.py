"""Input firewall for auto-capture pipeline.

Ported from neural-memory v4.58.0 safety/input_firewall.py.
Prevents garbage, oversized, or adversarial content from entering memory.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass

logger = logging.getLogger("super-memory.safety.firewall")

MAX_AUTO_CAPTURE_CHARS = 10_000
MIN_CONTENT_CHARS = 30
_REPETITION_RATIO_THRESHOLD = 0.3
_MIN_ENTROPY_THRESHOLD = 1.5

_CONTROL_SEQ_RE = re.compile(
    r"<ctrl\d+>"
    r"|<\/?(?:user|assistant|system|human|bot)\b[^>]*>"
    r"|\x00|\x01|\x02|\x03|\x04|\x05|\x06|\x07"
    r"|\x0e|\x0f|\x10|\x11|\x12|\x13|\x14|\x15|\x16|\x17|\x18|\x19|\x1a|\x1b|\x1c|\x1d|\x1e|\x1f",
    re.IGNORECASE,
)
_METADATA_INJECTION_RE = re.compile(
    r'"(?:sender_id|message_id|sender|recipient|chat_id)"\s*:'
    r'|"(?:role|type)"\s*:\s*"(?:user|assistant|system|tool)"'
    r"|Conversation\s+info\s*\((?:untrusted\s+)?metadata\)"
    r"|Sender\s*\((?:untrusted\s+)?metadata\)",
    re.IGNORECASE,
)
_BASE64_BLOCK_RE = re.compile(r"[A-Za-z0-9+/=]{100,}")
_NM_CONTEXT_NOISE_RE = re.compile(
    r"^#{1,3}\s*(?:Relevant Memories|Related Information|Relevant Context|Neural Memory)\b.*$"
    r"|^\[NeuralMemory\s*[\u2014\u2013\-].*\]$"
    r"|^-\s*\[(?:concept|entity|decision|error|preference|insight|memory|fact|workflow|instruction|pattern)\]\s"
    r"|^(?:Conversation info|Sender|Context)\s*\((?:untrusted\s+)?metadata\).*$",
    re.MULTILINE | re.IGNORECASE,
)

# Threat patterns — SQL injection, XSS, path traversal, shell injection
_THREAT_PATTERNS_RE = re.compile(
    r"\b(?:DROP\s+TABLE|ALTER\s+TABLE|DELETE\s+FROM|INSERT\s+INTO|TRUNCATE\s+TABLE|EXEC\s|UNION\s+SELECT)"
    r"|\brm\s+-rf\b|\bshutdown\b|\breboot\b|\bmkfs\b|\bdd\s+if="
    r"|(?:<script|<iframe|<embed|<object|<svg\s+onload)"
    r"|(?:\.\./|\.\.\\){2,}"
    r"|\bSELECT\s+.*\bFROM\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FirewallResult:
    blocked: bool
    reason: str = ""
    sanitized: str = ""


def check_content(text: str) -> FirewallResult:
    """Run all firewall checks on content destined for auto-capture."""
    try:
        if not text or not isinstance(text, str):
            return FirewallResult(blocked=True, reason="empty or non-string content")
        if len(text) > MAX_AUTO_CAPTURE_CHARS:
            return FirewallResult(blocked=True, reason=f"oversized ({len(text)} chars)")
        if len(text.strip()) < MIN_CONTENT_CHARS:
            return FirewallResult(blocked=True, reason="too short")
        control_matches = _CONTROL_SEQ_RE.findall(text)
        if len(control_matches) >= 2:
            return FirewallResult(blocked=True, reason=f"{len(control_matches)} control sequences")
        threat_matches = _THREAT_PATTERNS_RE.findall(text)
        if threat_matches:
            return FirewallResult(blocked=True, reason=f"threat pattern: {threat_matches[0][:40]}")
        metadata_matches = _METADATA_INJECTION_RE.findall(text)
        if len(metadata_matches) >= 2:
            return FirewallResult(blocked=True, reason="chat metadata patterns")
        base64_blocks = _BASE64_BLOCK_RE.findall(text)
        base64_chars = sum(len(b) for b in base64_blocks)
        if base64_chars > len(text) * 0.3:
            return FirewallResult(blocked=True, reason="mostly base64/binary")
        if _is_highly_repetitive(text):
            return FirewallResult(blocked=True, reason="highly repetitive")
        entropy = _char_entropy(text)
        if entropy < _MIN_ENTROPY_THRESHOLD and len(text) > 100:
            return FirewallResult(blocked=True, reason=f"low entropy ({entropy:.2f})")
        sanitized = _NM_CONTEXT_NOISE_RE.sub("", text)
        sanitized = _CONTROL_SEQ_RE.sub("", sanitized)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
        if len(sanitized.strip()) < MIN_CONTENT_CHARS:
            return FirewallResult(blocked=True, reason="too short after noise removal")
        return FirewallResult(blocked=False, sanitized=sanitized)
    except Exception as e:
        logger.warning(f"firewall.check_content error: {e}")
        return FirewallResult(blocked=True, reason=f"internal error: {e}")


def strip_nm_context_noise(text: str) -> str:
    """Strip noisy context markers from text before analysis."""
    if not text or not isinstance(text, str):
        return text
    cleaned = _NM_CONTEXT_NOISE_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def sanitize_explicit_content(text: str) -> str:
    """Sanitize content for explicit remember path (strips, does not block)."""
    if not text or not isinstance(text, str):
        return text
    sanitized = _CONTROL_SEQ_RE.sub("", text)
    sanitized = _METADATA_INJECTION_RE.sub("", sanitized)
    sanitized = _NM_CONTEXT_NOISE_RE.sub("", sanitized)
    return re.sub(r"\n{3,}", "\n\n", sanitized).strip()


def _is_highly_repetitive(text: str) -> bool:
    """Check if text is highly repetitive (low character variety)."""
    if len(text) < 100:
        return False
    sample = text[:5000]
    words = sample.lower().split()
    if len(words) < 10:
        return False
    trigrams: dict[str, int] = {}
    for i in range(len(words) - 2):
        gram = f"{words[i]} {words[i+1]} {words[i+2]}"
        trigrams[gram] = trigrams.get(gram, 0) + 1
    if not trigrams:
        return False
    total = sum(trigrams.values())
    max_count = max(trigrams.values())
    return max_count / total > _REPETITION_RATIO_THRESHOLD


def _char_entropy(text: str) -> float:
    """Compute character-level Shannon entropy of text."""
    if not text:
        return 0.0
    sample = text[:5000]
    freq: dict[str, int] = {}
    for ch in sample:
        freq[ch] = freq.get(ch, 0) + 1
    total = len(sample)
    entropy = 0.0
    for count in freq.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy
