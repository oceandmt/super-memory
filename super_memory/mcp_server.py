from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any, Callable

from . import bridge

JSON = dict[str, Any]

SERVER_INFO = {"name": "super-memory", "version": "0.1.0"}
PROTOCOL_VERSION = "2024-11-05"


def _text(content: Any) -> list[JSON]:
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, indent=2)
    return [{"type": "text", "text": content}]


def _schema(properties: JSON, required: list[str] | None = None) -> JSON:
    return {"type": "object", "properties": properties, "required": required or []}


TOOLS: dict[str, JSON] = {
    "super_memory_remember": {
        "description": "Save a memory through Super Memory canonical-first layer order.",
        "inputSchema": _schema(
            {
                "content": {"type": "string"},
                "type": {"type": "string", "default": "context"},
                "scope": {"type": "string", "default": "session"},
                "agent_id": {"type": "string", "default": "lucas"},
                "session_id": {"type": "string"},
                "project": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "source": {"type": "string"},
                "trust_score": {"type": "number"},
                "metadata": {"type": "object"},
                "config_path": {"type": "string"},
            },
            ["content"],
        ),
    },
    "super_memory_recall": {
        "description": "Recall memories from Super Memory layers.",
        "inputSchema": _schema(
            {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
                "config_path": {"type": "string"},
            },
            ["query"],
        ),
    },
    "super_memory_prefetch": {
        "description": "Merged/deduped Super Memory recall for prompt prefetch.",
        "inputSchema": _schema(
            {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
                "config_path": {"type": "string"},
            },
            ["query"],
        ),
    },
    "super_memory_sync_turn": {
        "description": "Save a compact multi-agent conversation turn event.",
        "inputSchema": _schema(
            {
                "agent_id": {"type": "string", "default": "lucas"},
                "session_id": {"type": "string"},
                "user_message": {"type": "string"},
                "assistant_message": {"type": "string"},
                "project": {"type": "string"},
                "metadata": {"type": "object"},
                "config_path": {"type": "string"},
            }
        ),
    },
    "super_memory_memory_search": {
        "description": "OpenClaw memory_search-compatible recall payload from Super Memory.",
        "inputSchema": _schema(
            {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
                "min_score": {"type": "number", "default": 0},
                "corpus": {"type": "string", "default": "all"},
                "config_path": {"type": "string"},
            },
            ["query"],
        ),
    },
    "super_memory_memory_get": {
        "description": "OpenClaw memory_get-compatible read from Super Memory virtual paths or workspace files.",
        "inputSchema": _schema(
            {
                "path": {"type": "string"},
                "from_line": {"type": "integer", "default": 1},
                "lines": {"type": "integer", "default": 20},
                "corpus": {"type": "string", "default": "all"},
                "config_path": {"type": "string"},
            },
            ["path"],
        ),
    },
    "super_memory_promote": {
        "description": "Promote a memory to MEMORY.md and the matching register.",
        "inputSchema": _schema({"memory_id": {"type": "string"}, "config_path": {"type": "string"}}, ["memory_id"]),
    },
    "super_memory_status": {
        "description": "Show Super Memory local status.",
        "inputSchema": _schema({"config_path": {"type": "string"}}),
    },
}


def _tool_descriptors() -> list[JSON]:
    return [{"name": name, **meta} for name, meta in TOOLS.items()]


def _call_tool(name: str, args: JSON) -> Any:
    if name == "super_memory_remember":
        config_path = args.pop("config_path", None)
        return bridge.remember(args, config_path=config_path)
    if name == "super_memory_recall":
        return bridge.recall(args["query"], limit=args.get("limit", 10), config_path=args.get("config_path"))
    if name == "super_memory_prefetch":
        return bridge.prefetch(args["query"], limit=args.get("limit", 10), config_path=args.get("config_path"))
    if name == "super_memory_sync_turn":
        config_path = args.pop("config_path", None)
        return bridge.sync_turn(args, config_path=config_path)
    if name == "super_memory_memory_search":
        return bridge.memory_search(
            args["query"],
            max_results=args.get("max_results", 5),
            min_score=args.get("min_score", 0.0),
            corpus=args.get("corpus", "all"),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_memory_get":
        return bridge.memory_get(
            args["path"],
            from_line=args.get("from_line", 1),
            lines=args.get("lines", 20),
            corpus=args.get("corpus", "all"),
            config_path=args.get("config_path"),
        )
    if name == "super_memory_promote":
        return bridge.promote(args["memory_id"], config_path=args.get("config_path"))
    if name == "super_memory_status":
        return bridge.status(config_path=args.get("config_path"))
    raise ValueError(f"unknown tool: {name}")


def _response(request_id: Any, result: Any) -> JSON:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, data: Any | None = None) -> JSON:
    payload: JSON = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    if data is not None:
        payload["error"]["data"] = data
    return payload


def handle(request: JSON) -> JSON | None:
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        return _response(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _response(request_id, {})
    if method == "tools/list":
        return _response(request_id, {"tools": _tool_descriptors()})
    if method == "tools/call":
        name = params.get("name")
        args = dict(params.get("arguments") or {})
        result = _call_tool(name, args)
        return _response(request_id, {"content": _text(result), "isError": False})
    if method == "resources/list":
        return _response(request_id, {"resources": [{"uri": "super-memory://status", "name": "Super Memory status", "mimeType": "application/json"}]})
    if method == "resources/read":
        uri = params.get("uri")
        if uri != "super-memory://status":
            return _error(request_id, -32602, f"unknown resource: {uri}")
        return _response(request_id, {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(bridge.status(), ensure_ascii=False, indent=2)}]})
    return _error(request_id, -32601, f"method not found: {method}")


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle(request)
        except Exception as exc:  # keep MCP transport alive and report as JSON-RPC error
            response = _error(None, -32000, str(exc), traceback.format_exc())
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Super Memory MCP stdio server")
    parser.add_argument("--stdio", action="store_true", help="Run stdio MCP server (default)")
    parser.parse_args(argv)
    serve()


if __name__ == "__main__":
    main()
