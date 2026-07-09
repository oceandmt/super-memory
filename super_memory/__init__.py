from __future__ import annotations
"""Super Memory: local multi-layer memory app for OpenClaw multi-agents.

Keep package import intentionally lightweight.  `python -m super_memory.mcp_server`
imports this package before running the stdio server; eagerly importing every
feature module here made MCP startup exceed the stdio contract test timeout on
slower/loaded machines.
"""

__version__ = "2.3.4"

from .models import MemoryLayer, MemoryRecord, MemoryScope, MemoryType
from .service import SuperMemoryService

__all__ = [
    "MemoryRecord",
    "MemoryLayer",
    "MemoryScope",
    "MemoryType",
    "SuperMemoryService",
]
