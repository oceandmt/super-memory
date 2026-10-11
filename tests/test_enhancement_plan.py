from super_memory import bridge, mcp_server


def test_enhancement_plan_contains_p0_p3_tests_commands_tools_and_final_recommendation():
    result = bridge.enhancement_plan()
    assert result["ok"] is True
    priorities = [item["priority"] for item in result["plan"]]
    assert priorities == ["P0", "P1", "P2", "P3"]
    for item in result["plan"]:
        assert item["deliverables"]
        assert item["suggested_tests"]
        assert item["operational_commands"]
        assert item["operational_tools"]
    assert result["recommended_next"]
    assert "P0" in result["final_recommendation"]


def test_enhancement_plan_mcp_tool_exposed():
    old = mcp_server.MCP_PROFILE
    try:
        mcp_server.MCP_PROFILE = "admin"
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        assert "super_memory_enhancement_plan" in names

        called = mcp_server.handle({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "super_memory_enhancement_plan", "arguments": {}},
        })
        assert called["result"]["isError"] is False
        payload = called["result"]["content"][0]["text"]
        assert "suggested_tests" in payload
        assert "final_recommendation" in payload
    finally:
        mcp_server.MCP_PROFILE = old
