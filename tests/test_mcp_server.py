import json
from pathlib import Path

from super_memory import mcp_server


def test_mcp_initialize_and_tools_list():
    init = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "super-memory"
    assert "tools" in init["result"]["capabilities"]

    tools = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert "super_memory_remember" in names
    assert "super_memory_memory_search" in names
    assert "super_memory_memory_get" in names
    assert "super_memory_status" in names


def test_mcp_tool_call_remember_and_search(tmp_path: Path):
    config = tmp_path / "super-memory.yaml"
    config.write_text(
        "workspace_root: \"{}\"\nsqlite_path: data/test.sqlite3\n".format(str(tmp_path).replace('\\', '\\\\')),
        encoding="utf-8",
    )
    remember = mcp_server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "super_memory_remember",
                "arguments": {
                    "content": "MCP server should expose Super Memory tools like neural-memory.",
                    "type": "decision",
                    "scope": "shared",
                    "config_path": str(config),
                },
            },
        }
    )
    assert remember["result"]["isError"] is False
    remember_payload = json.loads(remember["result"]["content"][0]["text"])
    assert remember_payload["record"]["content"].startswith("MCP server")

    search = mcp_server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "super_memory_memory_search",
                "arguments": {"query": "MCP server", "config_path": str(config)},
            },
        }
    )
    search_payload = json.loads(search["result"]["content"][0]["text"])
    assert search_payload["provider"] == "super-memory"
    assert search_payload["results"]


def test_mcp_resources_status(tmp_path: Path, monkeypatch):
    # resources/list is pure protocol coverage; status reads default project config.
    listed = mcp_server.handle({"jsonrpc": "2.0", "id": 5, "method": "resources/list"})
    assert listed["result"]["resources"][0]["uri"] == "super-memory://status"
