# Honcho - Conversational Memory Intelligence Layer
# Inspired by plastic-labs/honcho but local, no backend required

from .peer import PeerModel, PeerRole
from .dialectic import DialecticEngine, DialecticResult
from .session import SessionContextBuilder
from .insights import InsightGenerator

__all__ = [
    "PeerModel",
    "PeerRole",
    "DialecticEngine",
    "DialecticResult",
    "SessionContextBuilder",
    "InsightGenerator",
]
