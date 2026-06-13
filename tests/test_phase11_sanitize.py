from pathlib import Path

from super_memory import bridge, mcp_server
from super_memory.sanitize import normalize_memory_payload, sanitize_auto_capture, sanitize_prompt


def _config(tmp_path: Path) -> Path:
    cfg = tmp_path / "super-memory.yaml"
    cfg.write_text(f'workspace_root: "{tmp_path}"\nsqlite_path: data/test.sqlite3\n', encoding="utf-8")
    return cfg


def test_sanitize_prompt_and_auto_capture_redact_and_clean():
    text = "api_key=abc123456789 token: SECRET123456\r\nhello\x00   world"
    cleaned = sanitize_prompt(text)
    assert "abc123456789" not in cleaned
    assert "SECRET123456" not in cleaned
    assert "\x00" not in cleaned
    assert "hello world" in cleaned
    assert sanitize_auto_capture(text) == cleaned


def test_normalize_memory_payload_aliases_enums_tags_and_unknowns():
    normalized = normalize_memory_payload(
        {
            "content": " password=supersecret keep useful fact ",
            "memoryType": "task",
            "memoryScope": "cross_agent",
            "agentId": "Lucas",
            "sessionId": "s1",
            "trustScore": "1.7",
            "tags": "Phase One phase one SECURITY",
            "unexpected": "kept only as audit metadata",
        }
    )
    assert normalized["content"].startswith("password=[REDACTED]")
    assert normalized["type"] == "todo"
    assert normalized["scope"] == "cross-agent"
    assert normalized["agent_id"] == "Lucas"
    assert normalized["session_id"] == "s1"
    assert normalized["trust_score"] == 1.0
    assert normalized["tags"] == ["phase", "one", "security"]
    assert normalized["metadata"]["dropped_fields"] == ["unexpected"]


def test_remember_and_auto_use_normalized_schema(tmp_path: Path):
    cfg = _config(tmp_path)
    remembered = bridge.remember(
        {
            "content": "decision: normalize before save token=SHOULDREDACT",
            "memoryType": "decision-memory",
            "memoryScope": "global",
            "agentId": "lucas",
            "tags": "Schema Schema",
        },
        config_path=str(cfg),
    )
    assert remembered["record"]["type"] == "decision"
    assert remembered["record"]["scope"] == "shared"
    assert "SHOULDREDACT" not in remembered["record"]["content"]
    assert remembered["results"][0]["layer"] == "workspace_markdown"

    auto = bridge.auto("todo: capture safely secret=NOPE123456", save=True, config_path=str(cfg))
    assert auto["candidates"][0]["type"] == "todo"
    assert "NOPE123456" not in auto["candidates"][0]["content"]
    assert auto["saved"]["ok"] is True


def test_phase11_mcp_exposes_sanitize_and_normalize():
    old = mcp_server.MCP_PROFILE
    mcp_server.MCP_PROFILE = "normal"
    try:
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        assert "super_memory_sanitize_prompt" in names
        assert "super_memory_sanitize_auto_capture" in names
        assert "super_memory_normalize_memory" in names

        response = mcp_server.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "super_memory_normalize_memory",
                    "arguments": {"memory": {"content": "x", "memoryType": "task", "memoryScope": "global"}},
                },
            }
        )
        assert response["result"]["isError"] is False
        text = response["result"]["content"][0]["text"]
        assert '"type": "todo"' in text
        assert '"scope": "shared"' in text
    finally:
        mcp_server.MCP_PROFILE = old
