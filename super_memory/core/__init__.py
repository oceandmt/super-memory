"""Core domain package — canonical contracts for Super Memory architecture.

P0 modules:
- envelope.py: MemoryEnvelope v1 — quality/trust/provenance/lifecycle contract
"""

from .envelope import (
    MemoryEnvelope,
    MemoryScope,
    MemoryType,
    ProvenanceChain,
    LifecyclePolicy,
    Transformation,
    ProjectionStatus,
    build_envelope,
)
