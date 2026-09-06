"""MCP stdio 服务器: 把 PluginManager 里的插件自动暴露为 MCP 工具，
并提供 map_* 活地图编辑工具（经本地桥转发到 Web 工作台，见 docs/ai-editing.md）。

零依赖实现（标准库即可运行），协议为 newline-delimited JSON-RPC 2.0。

运行::

    spatialharness mcp           # 或 python -m spatialharness.mcp_server

前置条件（map_* 工具）::

    spatialharness serve                     # 桥需运行
    Web 工作台分析面板 → 「Python 分析」→ 勾选「AI 编辑」
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from . import __version__
from .core import PluginManager
from .wire import run_plugin_via_json, tool_description_for, tool_schema_for

PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = {PROTOCOL_VERSION, "2025-06-18"}

BRIDGE_URL = os.environ.get("SPATIALHARNESS_BRIDGE", "http://127.0.0.1:8765")
EDIT_TIMEOUT_S = 35.0

_PREREQ = (
    "前置: 1) 运行 spatialharness serve 2) Web 工作台(pnpm dev / gistudio.github.io/SpatialHarness)"
    " 分析面板勾选「AI 编辑」。编辑可通过 Ctrl+Z 撤销。坐标系 EPSG:4326。"
)

# ---------------------------------------------------------------------------
# map_* 工具定义（描述 + JSON Schema）
# ---------------------------------------------------------------------------

_GEOJSON_FEATURES = {
    "type": "array",
    "description": "GeoJSON Feature 数组（EPSG:4326）",
    "items": {"type": "object"},
}

MAP_TOOLS: Dict[str, Dict[str, Any]] = {
    "map_status": {
        "description": "检查 Web 工作台是否在线并返回工程概要。" + _PREREQ,
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    "map_get_project": {
        "description": "读取当前工程: 图层清单(id/name/几何类型/要素数/字段)与视图。编辑前先调用它拿 layerId。" + _PREREQ,
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    "map_add_features": {
        "description": "向已有图层追加要素(按 layerId 或 layerName 定位; 不存在则创建图层)。" + _PREREQ,
        "inputSchema": {
            "type": "object",
            "properties": {
                "layerId": {"type": "string", "description": "目标图层 id（来自 map_get_project）"},
                "layerName": {"type": "string", "description": "目标图层名（无 layerId 时使用）"},
                "features": _GEOJSON_FEATURES,
            },
            "required": ["features"],
        },
    },
    "map_replace_features": {
        "description": "整体替换图层全部要素。" + _PREREQ,
        "inputSchema": {
            "type": "object",
            "properties": {"layerId": {"type": "string"}, "features": _GEOJSON_FEATURES},
            "required": ["layerId", "features"],
        },
    },
    "map_update_features": {
        "description": "按 feature.id 匹配更新要素(合并 properties/替换 geometry)。" + _PREREQ,
        "inputSchema": {
            "type": "object",
            "properties": {"layerId": {"type": "string"}, "features": _GEOJSON_FEATURES},
            "required": ["layerId", "features"],
        },
    },
    "map_delete_features": {
        "description": "按 feature.id 删除要素。" + _PREREQ,
        "inputSchema": {
            "type": "object",
            "properties": {
                "layerId": {"type": "string"},
                "featureIds": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["layerId", "featureIds"],
        },
    },
    "map_add_layer": {
        "description": "新建矢量图层并载入要素(默认样式)。" + _PREREQ,
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "features": _GEOJSON_FEATURES,
                "style": {"type": "object", "description": "可选 LayerStyle JSON"},
            },
            "required": ["name", "features"],
        },
    },
    "map_remove_layer": {
        "description": "删除整个图层。" + _PREREQ,
        "inputSchema": {
            "type": "object",
            "properties": {"layerId": {"type": "string"}}, "required": ["layerId"],
        },
    },
    "map_set_layer_style": {
        "description": "设置图层样式: {symbol:{kind:'simple', pointColor|strokeColor|fillColor, strokeWidth|pointRadius}, label:null}。" + _PREREQ,
        "inputSchema": {
            "type": "object",
            "properties": {"layerId": {"type": "string"}, "style": {"type": "object"}},
            "required": ["layerId", "style"],
        },
    },
    "map_fit_layer": {
        "description": "缩放视图到指定图层(缺省全部图层)。" + _PREREQ,
        "inputSchema": {
            "type": "object",
            "properties": {"layerId": {"type": "string"}}, "required": [],
        },
    },
    "map_set_view": {
        "description": "设置视图: center=[lon,lat](EPSG:4326), zoom。" + _PREREQ,
        "inputSchema": {
            "type": "object",
            "properties": {
                "center": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                "zoom": {"type": "number"},
            },
            "required": ["center", "zoom"],
        },
    },
}


# 本地工具（无需浏览器/桥，headless 生成工程文件）
LOCAL_TOOLS: Dict[str, Dict[str, Any]] = {
    "write_project": {
        "description": (
            "headless 生成 SpatialHarness 工程文件 project.webgis.json（无需浏览器）。"
            "Web 工作台「打开数据文件夹」选中该文件所在目录即可载入。"
            "layers 为 [{name, features: GeoJSON Feature[](EPSG:4326), style?}]。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "输出 .json 路径或目录"},
                "name": {"type": "string", "description": "工程名"},
                "layers": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "[{name, features, style?}]",
                },
                "view": {"type": "object", "description": "可选 {center:[lon,lat], zoom}"},
            },
            "required": ["path", "name", "layers"],
        },
    },
}


def _handle_write_project(args: Dict[str, Any]) -> Dict[str, Any]:
    from .authoring import build_project, write_project

    project = build_project(
        args["name"], args["layers"], view=args.get("view") or None
    )
    path = write_project(project, args["path"])
    return {"path": path, "id": project["id"], "layers": len(project["layers"])}


def _bridge_edit(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """把编辑命令提交到本地桥并等待浏览器执行结果。"""
    payload = json.dumps({"tool": tool, "args": args, "wait": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{BRIDGE_URL}/edit/submit",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=EDIT_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", "")
        except Exception:  # noqa: BLE001
            detail = ""
        raise RuntimeError(f"桥返回 {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"无法连接本地桥 {BRIDGE_URL}: {exc.reason}。请先运行: spatialharness serve"
        ) from exc


def _tool_definitions(manager: PluginManager) -> list:
    tools = [
        {
            "name": info.name,
            "description": tool_description_for(manager.get(info.name)),
            "inputSchema": tool_schema_for(manager.get(info.name)),
        }
        for info in manager.list_plugins(only_enabled=True).values()
    ]
    tools.extend(
        {"name": name, **spec} for name, spec in sorted(MAP_TOOLS.items())
    )
    tools.extend(
        {"name": name, **spec} for name, spec in sorted(LOCAL_TOOLS.items())
    )
    return tools


def _handle_call(manager: PluginManager, arguments: Dict[str, Any]) -> Dict[str, Any]:
    name = arguments.get("name")
    call_args = arguments.get("arguments") or {}
    try:
        if name in LOCAL_TOOLS:
            if name == "write_project":
                result = _handle_write_project(call_args)
            else:  # pragma: no cover - 目前只有 write_project
                raise KeyError(name)
            text = json.dumps(result, ensure_ascii=False, default=str)
        elif name in MAP_TOOLS:
            result = _bridge_edit(name, call_args)
            if not result.get("ok", False):
                raise RuntimeError(str(result.get("error") or "编辑失败"))
            text = json.dumps(result.get("result", result.get("summary", {})), ensure_ascii=False, default=str)
        else:
            result = run_plugin_via_json(
                manager, name, call_args.get("data"), call_args.get("params")
            )
            text = json.dumps(result, ensure_ascii=False, default=str)
        return {
            "content": [{"type": "text", "text": text}],
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
