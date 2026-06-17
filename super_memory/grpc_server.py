"""gRPC server stub for Super-Memory.

Provides a MemoryService with Remember, Recall, Forget, Search, Status RPCs.
Uses grpc.aio for async operation. No heavy .proto compilation — the service
class is defined directly with async methods.

Start with: super-memory --grpc  (alongside REST API)
Or standalone: SUPER_MEMORY_GRPC_PORT=50052 python -m super_memory.grpc_server
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
from typing import Any

logger = logging.getLogger("super-memory.grpc")


class MemoryService:
    """MemoryService with async RPC methods.

    Each method mirrors the bridge.py API surface.
    This is a stub/skeleton — doesn't require proto compilation.
    When grpcio is installed, this class can be registered with
    grpc.aio.server() using the generic handler pattern.
    """

    # Discovery: list available RPC methods
    _RPC_METHODS = {
        "Remember": {
            "description": "Store a memory across all configured layers",
            "request_fields": ["content", "type", "scope", "agent_id", "session_id", "tags"],
            "response_fields": ["record", "results", "graph_projection"],
        },
        "Recall": {
            "description": "Recall memories matching a query across layers",
            "request_fields": ["query", "limit"],
            "response_fields": ["layers", "results"],
        },
        "Forget": {
            "description": "Delete a memory (soft or hard)",
            "request_fields": ["memory_id", "hard", "reason"],
            "response_fields": ["ok", "memory_id", "action"],
        },
        "Search": {
            "description": "Semantic search over memory index",
            "request_fields": ["query", "max_results", "min_score", "corpus"],
            "response_fields": ["results"],
        },
        "Status": {
            "description": "Get memory store statistics and health",
            "request_fields": [],
            "response_fields": ["total_memories", "layers", "graph_edges", "cognitive_synapses"],
        },
    }

    async def Remember(self, request: dict[str, Any]) -> dict[str, Any]:
        """Store a memory. Delegates to bridge.remember()."""
        from . import bridge
        result = bridge.remember(dict(request))
        return result

    async def Recall(self, request: dict[str, Any]) -> dict[str, Any]:
        """Recall memories. Delegates to bridge.recall()."""
        from . import bridge
        result = bridge.recall(
            request.get("query", ""),
            limit=request.get("limit", 10),
        )
        return result

    async def Forget(self, request: dict[str, Any]) -> dict[str, Any]:
        """Forget a memory. Delegates to bridge.forget()."""
        from . import bridge
        result = bridge.forget(
            request.get("memory_id", ""),
            hard=request.get("hard", False),
            reason=request.get("reason", ""),
        )
        return result

    async def Search(self, request: dict[str, Any]) -> dict[str, Any]:
        """Search memories. Delegates to bridge.memory_search()."""
        from . import bridge
        result = bridge.memory_search(
            request.get("query", ""),
            max_results=request.get("max_results", 5),
            min_score=request.get("min_score", 0.0),
            corpus=request.get("corpus", "all"),
        )
        return result

    async def Status(self, request: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get status. Delegates to bridge.status()."""
        from . import bridge
        return bridge.status()


class GenericGRPCServer:
    """Generic gRPC server wrapper using the grpc.aio reflection approach.

    When grpcio is installed, this binds MemoryService methods to gRPC.
    Otherwise, it logs a warning and acts as a no-op.
    """

    def __init__(self, address: str = "127.0.0.1:50051"):
        self.address = address
        self._server = None
        self._service = MemoryService()

    async def start(self) -> None:
        """Start the gRPC server on the configured address."""
        try:
            if importlib.util.find_spec("grpc") is not None:
                # Use generic handler — no proto compilation needed
                logger.info(
                    "gRPC server would start on %s with methods: %s",
                    self.address,
                    list(self._service._RPC_METHODS.keys()),
                )
            else:
                raise ImportError("grpcio not found")
            # Placeholder for actual grpc.aio.server() + add_generic_rpc_handlers()
        except ImportError:
            logger.warning(
                "grpcio not installed — gRPC server unavailable. "
                "Install with: pip install grpcio"
            )

    async def stop(self) -> None:
        """Stop the gRPC server."""
        if self._server is not None:
            await self._server.stop(0)
            self._server = None


def start(port: int | None = None) -> GenericGRPCServer:
    """Create and return a gRPC server instance bound to 127.0.0.1.

    Port defaults to SUPER_MEMORY_GRPC_PORT env or 50051.
    """
    if port is None:
        port = int(os.environ.get("SUPER_MEMORY_GRPC_PORT", "50051"))
    address = f"127.0.0.1:{port}"
    logger.info("gRPC server configured for %s", address)
    return GenericGRPCServer(address)


async def _run_grpc(port: int | None = None) -> None:
    server = start(port=port)
    await server.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await server.stop()


def run_sync(port: int | None = None) -> None:
    """Synchronous entry point for CLI."""
    asyncio.run(_run_grpc(port=port))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run_grpc())
