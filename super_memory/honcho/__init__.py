from __future__ import annotations
# Honcho - Conversational Memory Intelligence Layer
# Inspired by plastic-labs/honcho but local, no backend required

from .dialectic import DialecticEngine, DialecticResult
from .insights import InsightGenerator
from .peer import PeerModel, PeerRole
from .session import SessionContextBuilder

__all__ = [
    "PeerModel",
    "PeerRole",
    "DialecticEngine",
    "DialecticResult",
    "SessionContextBuilder",
    "InsightGenerator",
]
