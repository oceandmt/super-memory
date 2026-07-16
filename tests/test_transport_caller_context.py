from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from super_memory import mcp_server
from super_memory.api import app


def _config(tmp_path: Path) -> Path:
    config = tmp_path / "super-memory.yaml"
    config.write_text(
        f'workspace_root: "{tmp_path}"\nsqlite_path: data/test.sqlite3\n',
        encoding="utf-8",
    )
    return config


def _mcp_call(name: str, arguments: dict, request_id: int) -> dict:
    response = mcp_server.handle(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert "error" not in response, response
    assert response["result"]["isError"] is False, response
    return json.loads(response["result"]["content"][0]["text"])


def test_api_forwards_project_caller_context(tmp_path: Path) -> None:
    config = _config(tmp_path)
    client = TestClient(app)
    payload = {
        "content": "Transport project visibility sentinel API.",
        "type": "decision",
        "scope": "project",
        "agent_id": "lucas",
        "project": "transport-project",
        "config_path": str(config),
    }
    saved = client.post("/remember", json=payload)
    assert saved.status_code == 200
    memory_id = saved.json()["record"]["id"]

    hidden = client.post(
        "/memory-search",
        json={"query": "visibility sentinel API", "config_path": str(config)},
    )
    assert hidden.status_code == 200
    assert hidden.json()["results"] == []

    visible = client.post(
        "/memory-search",
        json={
            "query": "visibility sentinel API",
            "project": "transport-project",
            "scope": "project",
            "config_path": str(config),
        },
    )
    assert visible.status_code == 200
    assert any(item["memory_id"] == memory_id for item in visible.json()["results"])

    anonymous_show = client.post(
        "/show", json={"memory_id": memory_id, "config_path": str(config)}
    )
    assert anonymous_show.status_code == 200
    assert anonymous_show.json()["ok"] is False

    owner_show = client.post(
        "/show",
        json={
            "id": memory_id,
            "project": "transport-project",
            "scope": "project",
            "config_path": str(config),
        },
    )
    assert owner_show.status_code == 200
    assert owner_show.json()["ok"] is True


def test_mcp_forwards_project_caller_context(tmp_path: Path) -> None:
    config = _config(tmp_path)
    old_profile = mcp_server.MCP_PROFILE
    mcp_server.MCP_PROFILE = "normal"
    try:
        saved = _mcp_call(
            "super_memory_remember",
            {
                "content": "Transport project visibility sentinel MCP.",
                "type": "decision",
                "scope": "project",
                "agent_id": "lucas",
                "project": "transport-project",
                "config_path": str(config),
            },
            1,
        )
        memory_id = saved["record"]["id"]

        hidden = _mcp_call(
            "super_memory_memory_search",
            {"query": "visibility sentinel MCP", "config_path": str(config)},
            2,
        )
        assert hidden["results"] == []

        visible = _mcp_call(
            "super_memory_memory_search",
            {
                "query": "visibility sentinel MCP",
                "project": "transport-project",
                "scope": "project",
                "config_path": str(config),
            },
            3,
        )
        assert any(item["memory_id"] == memory_id for item in visible["results"])

        anonymous_show = _mcp_call(
            "super_memory_show",
            {"memory_id": memory_id, "config_path": str(config)},
            4,
        )
        assert anonymous_show["ok"] is False

        owner_show = _mcp_call(
            "super_memory_show",
            {
                "memory_id": memory_id,
                "project": "transport-project",
                "scope": "project",
                "config_path": str(config),
            },
            5,
        )
        assert owner_show["ok"] is True
    finally:
        mcp_server.MCP_PROFILE = old_profile
