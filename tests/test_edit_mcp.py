from __future__ import annotations

import json

import pytest

from spatialharness.core import PluginManager
from spatialharness.mcp_server import MAP_TOOLS, dispatch

MUTATING = {
    "map_add_features", "map_replace_features", "map_update_features",
    "map_delete_features", "map_add_layer", "map_remove_layer", "map_set_layer_style",
}


def _mgr() -> PluginManager:
    return PluginManager(extra_dirs=[], auto_load=True)


def test_map_tools_listed():
    result = dispatch(_mgr(), "tools/list", {})
    names = [t["name"] for t in result["tools"]]
    assert set(MAP_TOOLS) <= set(names)
    assert "write_project" in names  # L2 本地工具也在清单里


def test_map_tool_without_bridge_gives_actionable_error():
    """桥未运行时, 编辑工具返回 isError + 启动提示（而不是崩溃）。"""
    result = dispatch(_mgr(), "tools/call", {"name": "map_status", "arguments": {}})
    assert result["isError"] is True
    assert "spatialharness serve" in result["content"][0]["text"]


def test_map_tool_success_via_bridge(monkeypatch):
    import spatialharness.mcp_server as m

    def fake_bridge(tool, args):
        return {"ok": True, "result": {"browser_connected": True, "layers": 2}}

    monkeypatch.setattr(m, "_bridge_edit", fake_bridge)
    result = dispatch(_mgr(), "tools/call", {"name": "map_status", "arguments": {}})
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["layers"] == 2


def test_map_tool_bridge_failure_propagates(monkeypatch):
    import spatialharness.mcp_server as m

    monkeypatch.setattr(m, "_bridge_edit", lambda tool, args: {"ok": False, "error": "浏览器未连接"})
    result = dispatch(_mgr(), "tools/call", {"name": "map_add_features", "arguments": {}})
    assert result["isError"] is True
    assert "浏览器未连接" in result["content"][0]["text"]


def test_write_project_local_tool(tmp_path):
    out = tmp_path / "proj.json"
    result = dispatch(_mgr(), "tools/call", {"name": "write_project", "arguments": {
        "path": str(out),
        "name": "测试工程",
        "layers": [{"name": "城市", "features": [
            {"type": "Feature", "properties": {"n": "a", "v": 1},
             "geometry": {"type": "Point", "coordinates": [116.4, 39.9]}}
        ]}],
    }})
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["layers"] == 1
    project = json.loads(out.read_text(encoding="utf-8"))
    assert project["app"] == "spatial-harness"
    assert project["name"] == "测试工程"
    layer = project["layers"][0]
    assert layer["geometryType"] == "Point"
    assert {"name": "n", "type": "string"} in layer["fields"]
    assert {"name": "v", "type": "number"} in layer["fields"]
