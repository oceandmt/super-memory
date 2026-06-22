from __future__ import annotations
"""Safety subsystem — input firewall, freshness, brain scanner, encryption.

Ported from neural-memory v4.58.0 safety/.
Non-blocking: all features degrade gracefully if dependencies missing.
"""
from .firewall import check_content, sanitize_explicit_content, strip_nm_context_noise, FirewallResult
from .freshness import evaluate_freshness, format_age, analyze_freshness, FreshnessLevel, FreshnessResult
from .encryption import MemoryEncryptor, EncryptionManager

__all__ = [
    "check_content", "sanitize_explicit_content", "strip_nm_context_noise", "FirewallResult",
    "evaluate_freshness", "format_age", "analyze_freshness", "FreshnessLevel", "FreshnessResult",
    "MemoryEncryptor", "EncryptionManager",
]
