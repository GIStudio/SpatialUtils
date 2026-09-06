"""MCP stdio 服务器: 把 PluginManager 里的插件自动暴露为 MCP 工具。

零依赖实现（标准库即可运行），协议为 newline-delimited JSON-RPC 2.0，
兼容 MCP initialize / tools/list / tools/call / ping。

运行::

    spatialharness mcp           # 或 python -m spatialharness.mcp_server

在支持 MCP 的 AI 客户端（Claude Code / Codex / DeepSeek Harness 等）里
以 stdio 方式注册该命令即可调用全部插件。
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from . import __version__
from .core import PluginManager
from .wire import run_plugin_via_json, tool_description_for, tool_schema_for

PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = {PROTOCOL_VERSION, "2025-06-18"}


def _tool_definitions(manager: PluginManager) -> list:
    return [
        {
            "name": info.name,
            "description": tool_description_for(manager.get(info.name)),
            "inputSchema": tool_schema_for(manager.get(info.name)),
        }
        for info in manager.list_plugins(only_enabled=True).values()
    ]


def _handle_call(manager: PluginManager, arguments: Dict[str, Any]) -> Dict[str, Any]:
    name = arguments.get("name")
    call_args = arguments.get("arguments") or {}
    try:
        result = run_plugin_via_json(
            manager, name, call_args.get("data"), call_args.get("params")
        )
        return {
            "content": [
                {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}
            ],
            "isError": False,
        }
    except Exception as exc:  # noqa: BLE001 - 错误要回传给模型而不是杀死服务器
        return {
            "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
            "isError": True,
        }


def dispatch(manager: PluginManager, method: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """处理一条请求/通知；通知返回 None（不应答）。"""
    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        requested = params.get("protocolVersion", PROTOCOL_VERSION)
        return {
            "protocolVersion": requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "spatialharness", "version": __version__},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": _tool_definitions(manager)}
    if method == "tools/call":
        return _handle_call(manager, params)
    raise KeyError(f"method not found: {method}")


def serve_stdio(manager: Optional[PluginManager] = None) -> int:
    """stdin/stdout 主循环；返回进程退出码。"""
    manager = manager or PluginManager()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"parse error: {exc}"}}
            print(json.dumps(response, ensure_ascii=False), flush=True)
            continue
        msg_id = message.get("id")
        method = message.get("method", "")
        try:
            result = dispatch(manager, method, message.get("params") or {})
            if msg_id is None:  # 通知或无 id 请求
                continue
            response: Dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except KeyError as exc:
            response = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": str(exc)}}
        except Exception as exc:  # noqa: BLE001 - 内部错误按协议回传
            response = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": f"{type(exc).__name__}: {exc}"}}
        print(json.dumps(response, ensure_ascii=False, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(serve_stdio())
