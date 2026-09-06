from __future__ import annotations

import json
import subprocess
import sys

from spatialharness.core import PluginManager
from spatialharness.mcp_server import dispatch


def _mgr() -> PluginManager:
    return PluginManager(extra_dirs=[], auto_load=True)


def test_initialize_handshake():
    result = dispatch(_mgr(), "initialize", {"protocolVersion": "2024-11-05"})
    assert result["serverInfo"]["name"] == "spatialharness"
    assert "tools" in result["capabilities"]


def test_initialize_unknown_version_falls_back():
    result = dispatch(_mgr(), "initialize", {"protocolVersion": "1999-01-01"})
    assert result["protocolVersion"] == "2024-11-05"


def test_notification_returns_none():
    assert dispatch(_mgr(), "notifications/initialized", {}) is None


def test_ping():
    assert dispatch(_mgr(), "ping", {}) == {}


def test_tools_list_exposes_plugins():
    tools = dispatch(_mgr(), "tools/list", {})["tools"]
    names = [t["name"] for t in tools]
    assert "spatial_accessibility" in names
    assert "street_solar" in names
    tool = next(t for t in tools if t["name"] == "street_solar")
    assert "folder=path" in tool["inputSchema"]["properties"]["data"]["description"]


def test_tools_call_hello():
    result = dispatch(_mgr(), "tools/call", {
        "name": "hello",
        "arguments": {"params": {"who": "MCP"}},
    })
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["message"].startswith("Hello, MCP!")


def test_tools_call_error_reported_not_raised():
    result = dispatch(_mgr(), "tools/call", {"name": "no_such_plugin", "arguments": {}})
    assert result["isError"] is True
    assert "no_such_plugin" in result["content"][0]["text"]


def test_unknown_method_raises_keyerror():
    try:
        dispatch(_mgr(), "resources/list", {})
        raised = False
    except KeyError:
        raised = True
    assert raised


def test_stdio_subprocess_end_to_end():
    """真实子进程: newline-JSON 进 → newline-JSON 出（MCP stdio 传输）。"""
    lines = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "hello", "arguments": {"params": {"who": "stdio"}}}}),
    ]) + "\n"
    proc = subprocess.run(
        [sys.executable, "-m", "spatialharness.mcp_server"],
        input=lines, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    responses = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
    assert len(responses) == 3  # 通知不应答
    assert responses[0]["result"]["serverInfo"]["name"] == "spatialharness"
    names = [t["name"] for t in responses[1]["result"]["tools"]]
    assert "hello" in names
    call = json.loads(responses[2]["result"]["content"][0]["text"])
    assert "stdio" in call["message"]
