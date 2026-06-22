"""Handler base: ToolHandler ABC + ToolRegistry for handler-per-tool dispatch.

Replaces the 148-line if-else chain in mcp_server.py with a
registry-based dispatch pattern. Each MCP tool gets a lightweight
handler class that owns its name, schema, and dispatch logic.

Architecture::

    ToolHandler (ABC)
      ├── name: str
      ├── description: str
      ├── input_schema: dict
      ├── required: list[str]
      └── handle(args) → dict

    ToolRegistry
      ├── register(handler)
      ├── dispatch(name, args) → dict
      ├── get_tools(profile) → list[tool_def]
      └── get_schema(name) → dict
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any


class ToolHandler(ABC):
    """Abstract base for a single MCP tool handler."""

    name: str = ""
    description: str = ""
    required: list[str] = []
    properties: dict[str, Any] = {}
    admin_only: bool = False  # ADMIN_TOOLS
    advanced: bool = False    # ADVANCED_TOOLS (implies admin)

    @abstractmethod
    def handle(self, args: dict[str, Any]) -> Any:
        """Execute the tool with parsed args. Returns JSON-serializable result."""
        ...

    def input_schema(self) -> dict[str, Any]:
        """Build MCP inputSchema from properties."""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {},
        }
        for k, v in self.properties.items():
            schema["properties"][k] = v
        if self.required:
            schema["required"] = list(self.required)
        return schema

    def __repr__(self) -> str:
        return f"<ToolHandler {self.name}>"


class ToolRegistry:
    """Registry of ToolHandler instances with profile-based access control."""

    def __init__(self):
        self._handlers: dict[str, ToolHandler] = {}
        self._groups: dict[str, set[str]] = {
            "normal": set(),
            "admin": set(),
            "readonly": set(),
        }

    # ── Registration ──────────────────────────────────────────────────

    def register(self, handler: ToolHandler) -> ToolHandler:
        """Register a tool handler."""
        self._handlers[handler.name] = handler
        # Assign to access groups
        self._groups["normal"].add(handler.name)
        self._groups["admin"].add(handler.name)
        self._groups["readonly"].add(handler.name)

        if handler.advanced:
            # Advanced tools: admin-only (not normal, not readonly)
            self._groups["normal"].discard(handler.name)
            self._groups["readonly"].discard(handler.name)

        if handler.admin_only:
            # Admin-only: not normal, not advanced, not readonly
            self._groups["normal"].discard(handler.name)
            self._groups["readonly"].discard(handler.name)

        return handler

    def register_batch(self, handlers: list[ToolHandler]) -> None:
        """Register multiple handlers at once."""
        for h in handlers:
            self.register(h)

    # ── Dispatch ──────────────────────────────────────────────────────

    def dispatch(self, name: str, args: dict[str, Any]) -> Any:
        """Find handler and execute. Raises KeyError if unknown."""
        handler = self._handlers.get(name)
        if handler is None:
            raise KeyError(f"unknown tool: {name}")
        return handler.handle(args)

    def get(self, name: str) -> ToolHandler | None:
        """Get handler by name."""
        return self._handlers.get(name)

    def has(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._handlers

    # ── Schema / Tool Listing ─────────────────────────────────────────

    def list_tools(self, profile: str = "normal") -> list[dict[str, Any]]:
        """List tool definitions for the given profile."""
        allowed = self._groups.get(profile, self._groups["normal"])
        tools = []
        for name in sorted(allowed):
            h = self._handlers[name]
            tools.append({
                "name": name,
                "description": h.description,
                "inputSchema": h.input_schema(),
            })
        return tools

    def get_schema(self, name: str) -> dict[str, Any] | None:
        """Get MCP inputSchema for a tool."""
        h = self._handlers.get(name)
        if not h:
            return None
        return h.input_schema()

    def get_all_names(self) -> list[str]:
        """Get all registered tool names (sorted)."""
        return sorted(self._handlers.keys())

    # ── Profile / Access ──────────────────────────────────────────────

    def has_profile(self, name: str, profile: str = "normal") -> bool:
        """Check if a tool is accessible to a profile."""
        allowed = self._groups.get(profile, set())
        return name in allowed

    def get_profile_set(self, profile: str = "normal") -> set[str]:
        """Get all tool names for a profile."""
        return set(self._groups.get(profile, self._groups["normal"]))


# ── Convenience subclass for simple handlers ─────────────────────────────────

class SimpleHandler(ToolHandler):
    """Handler that wraps a callable.

    Useful for migrating existing bridge functions without rewriting.
    """

    def __init__(
        self,
        name: str,
        description: str,
        handler_fn: callable,
        properties: dict[str, Any] | None = None,
        required: list[str] | None = None,
        admin_only: bool = False,
        advanced: bool = False,
        arg_map: dict[str, str] | None = None,
    ):
        self.name = name
        self.description = description
        self._handler_fn = handler_fn
        self.properties = properties or {}
        self.required = required or []
        self.admin_only = admin_only
        self.advanced = advanced
        self._arg_map = arg_map or {}

    def handle(self, args: dict[str, Any]) -> Any:
        mapped = {}
        for k, v in args.items():
            target = self._arg_map.get(k, k)
            mapped[target] = v
        return self._handler_fn(**mapped)
