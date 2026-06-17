"""P4#3 — gRPC server stub test.

Verifies that the grpc_server module can be imported and instantiated.
No real gRPC connection is made (grpcio may not be installed).
"""

from __future__ import annotations

import asyncio

import pytest


def test_grpc_server_imports():
    """grpc_server module imports cleanly."""
    from super_memory.grpc_server import GenericGRPCServer, MemoryService, start

    assert MemoryService is not None
    assert GenericGRPCServer is not None
    assert start is not None


def test_memory_service_has_expected_rpcs():
    """MemoryService exposes the 5 expected RPC methods."""
    from super_memory.grpc_server import MemoryService

    svc = MemoryService()
    assert set(svc._RPC_METHODS.keys()) == {"Remember", "Recall", "Forget", "Search", "Status"}


def test_memory_service_methods_are_async():
    """Each RPC method should be a coroutine function."""
    import inspect

    from super_memory.grpc_server import MemoryService

    svc = MemoryService()
    for rpc_name in svc._RPC_METHODS:
        method = getattr(svc, rpc_name)
        assert callable(method), f"{rpc_name} is not callable"


def test_start_returns_server():
    """start() returns a GenericGRPCServer with the correct address."""
    from super_memory.grpc_server import start

    server = start(port=50052)
    assert isinstance(server, type(start(port=50052)))
    assert "127.0.0.1" in server.address
    assert "50052" in server.address


def test_default_port_from_env(monkeypatch: pytest.MonkeyPatch):
    """start() respects SUPER_MEMORY_GRPC_PORT env var."""
    monkeypatch.setenv("SUPER_MEMORY_GRPC_PORT", "9999")
    from super_memory.grpc_server import start

    server = start()
    assert "127.0.0.1:9999" == server.address


def test_generic_server_service_attribute():
    """GenericGRPCServer has a MemoryService instance."""
    from super_memory.grpc_server import GenericGRPCServer, MemoryService

    server = GenericGRPCServer("127.0.0.1:50051")
    assert isinstance(server._service, MemoryService)
