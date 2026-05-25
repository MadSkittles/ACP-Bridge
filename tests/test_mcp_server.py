from acp_bridge.mcp_server import build_server


def test_mcp_server_registers_remote_agent_tools() -> None:
    server = build_server()

    tool_names = {tool.name for tool in server._tool_manager.list_tools()}

    assert "remote_agent_list" in tool_names
    assert "remote_agent_ping" in tool_names
    assert "remote_agent_run" in tool_names
    assert "remote_agent_cancel" in tool_names
