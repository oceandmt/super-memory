import json
from pathlib import Path

from super_memory import mcp_server


def test_mcp_initialize_and_tools_list():
    mcp_server.MCP_PROFILE = "normal"
    init = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "super-memory"
    assert "tools" in init["result"]["capabilities"]

    tools = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert "super_memory_remember" in names
    assert "super_memory_memory_search" in names
    assert "super_memory_memory_get" in names
    assert "super_memory_status" in names
    assert "super_memory_promote" not in names


def test_mcp_admin_profile_exposes_promote():
    old = mcp_server.MCP_PROFILE
    try:
        mcp_server.MCP_PROFILE = "admin"
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 20, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        assert "super_memory_promote" in names
    finally:
        mcp_server.MCP_PROFILE = old


def test_mcp_curated_profile_is_accepted_by_cli():
    """Regression: `--profile curated` must be a valid argparse choice.

    CURATED_TOOLS and the `_allowed_tools` branch shipped before `curated` was
    added to the argparse `choices` list, so the stdio server crashed at
    startup with "invalid choice: 'curated'" whenever a client configured that
    profile. OpenClaw was configured with `--profile curated` and failed with
    "Connection closed".
    """
    import subprocess
    import sys

    # Assert on the usage line (the argparse choice list), not just any mention
    # of the word "curated" — the help text mentions it too, which would let a
    # broken choices list slip through.
    proc = subprocess.run(
        [sys.executable, "-m", "super_memory.mcp_server", "--help"],
        text=True,
        capture_output=True,
        timeout=30,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    usage_line = next(
        (line for line in proc.stdout.splitlines() if "--profile" in line),
        "",
    )
    assert "curated" in usage_line, proc.stdout

    # And prove the server actually starts under the curated profile.
    init = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
        }
    )
    started = subprocess.run(
        [sys.executable, "-m", "super_memory.mcp_server", "--stdio", "--profile", "curated"],
        input=init + "\n",
        text=True,
        capture_output=True,
        timeout=60,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert started.returncode == 0, started.stdout + started.stderr
    assert "invalid choice" not in (started.stdout + started.stderr)


def test_mcp_curated_profile_exposes_capture_and_core_tools():
    old = mcp_server.MCP_PROFILE
    try:
        mcp_server.MCP_PROFILE = "curated"
        names = {t["name"] for t in mcp_server._tool_descriptors()}
    finally:
        mcp_server.MCP_PROFILE = old
    # Auto-capture tools must be present or memory capture silently breaks.
    for required in (
        "super_memory_remember",
        "super_memory_recall",
        "super_memory_capture_event",
        "super_memory_capture_turn",
        "super_memory_sync_turn",
    ):
        assert required in names, required
    # Promotion is intentionally included in the curated set.
    assert "super_memory_promote" in names
    assert names <= {t["name"] for t in mcp_server._tool_descriptors("admin")}


def test_mcp_normal_profile_blocks_admin_tool_call():
    old = mcp_server.MCP_PROFILE
    try:
        mcp_server.MCP_PROFILE = "normal"
        response = mcp_server.handle(
            {
                "jsonrpc": "2.0",
                "id": 21,
                "method": "tools/call",
                "params": {"name": "super_memory_promote", "arguments": {"memory_id": "x"}},
            }
        )
        assert response["error"]["code"] == -32000
    finally:
        mcp_server.MCP_PROFILE = old


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


def test_mcp_stdio_stdout_is_json_only(tmp_path: Path):
    """Regression: MCP stdout must be JSON-RPC only, never structured logs."""
    import json as _json
    import subprocess
    import sys

    config = tmp_path / "super-memory.yaml"
    config.write_text(
        "workspace_root: \"{}\"\nsqlite_path: data/test.sqlite3\n".format(str(tmp_path).replace('\\', '\\\\')),
        encoding="utf-8",
    )
    request = {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "tools/call",
        "params": {
            "name": "super_memory_memory_search",
            "arguments": {"query": "stdio contract", "max_results": 1, "config_path": str(config)},
        },
    }
    proc = subprocess.run(
        [sys.executable, "-m", "super_memory.mcp_server", "--stdio", "--profile", "admin"],
        input=_json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        timeout=15,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0
    stdout_lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert len(stdout_lines) == 1, proc.stdout
    parsed = _json.loads(stdout_lines[0])
    assert parsed["id"] == 42
    assert "[info" not in proc.stdout
    assert "memory_op" not in proc.stdout


def test_default_config_is_project_local_when_no_config(monkeypatch, tmp_path: Path):
    from super_memory.config import load_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SUPER_MEMORY_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("SUPER_MEMORY_SQLITE_PATH", raising=False)
    cfg = load_config(path=tmp_path / "missing-super-memory.yaml")
    assert cfg.workspace_root == tmp_path
    assert cfg.sqlite_path == "data/super-memory.sqlite3"
