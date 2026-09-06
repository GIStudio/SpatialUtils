"""headless 工程文件生成（L2，见 docs/ai-editing.md）。

直接产出 SpatialHarness Web 工作台的 `project.webgis.json`
（ProjectFile v1 格式），无需浏览器。Web 端「打开数据文件夹」即可载入。
与 L1 的 map_get_project 共用同一 LayerModel 形状。

用法::

    from spatialharness.authoring import build_project, write_project
    project = build_project("我的工程", layers=[{"name": "城市", "features": [...] }])
    write_project(project, "D:/maps/project.webgis.json")
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

GEOMETRY_TYPES = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}


def _infer_geometry_type(features: List[Dict[str, Any]]) -> str:
    types = set()
    for f in features:
        geom = f.get("geometry") or {}
        t = geom.get("type")
        if t in GEOMETRY_TYPES:
            types.add("Point" if t in ("Point", "MultiPoint") else
                      "LineString" if t in ("LineString", "MultiLineString") else "Polygon")
    if not types:
        return "None"
    if len(types) == 1:
        return types.pop()
    return "Mixed"


def _infer_fields(features: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """从要素属性采样推断字段名与类型（与 Web 端 FieldInfo 对齐）。"""
    fields: Dict[str, str] = {}
    for f in features:
        for key, value in (f.get("properties") or {}).items():
            py_type = type(value).__name__
            ft = {"str": "string", "int": "number", "float": "number", "bool": "boolean"}.get(py_type)
            if ft is None:
                continue
            if key not in fields:
                fields[key] = ft
            elif fields[key] != ft:
                fields[key] = "string" if "string" in (fields[key], ft) else ft
    return [{"name": k, "type": v} for k, v in fields.items()]


def _default_style(geometry_type: str) -> Dict[str, Any]:
    """与 Web 端分析结果图层一致的默认样式（DEFAULT_PALETTE 首色 #... 用具体色值）。"""
    color = "#3b82f6"
    if geometry_type == "Point":
        return {"symbol": {"kind": "simple", "pointSymbol": "circle", "pointRadius": 5, "pointColor": color}, "label": None}
    if geometry_type == "LineString":
        return {"symbol": {"kind": "simple", "strokeColor": color, "strokeWidth": 2}, "label": None}
    return {"symbol": {"kind": "simple", "fillColor": color, "strokeColor": color, "strokeWidth": 1}, "label": None}


def _uid(prefix: str) -> str:
    return f"{prefix}_{os.urandom(6).hex()}"


def build_vector_layer(
    name: str,
    features: List[Dict[str, Any]],
    style: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造一个矢量 LayerModel（与 Web 端 VectorLayerModel 字段对齐）。"""
    now = int(time.time() * 1000)
    geometry_type = _infer_geometry_type(features)
    return {
        "id": _uid("lyr"),
        "name": name,
        "kind": "vector",
        "geometryType": geometry_type,
        "features": features,
        "fields": _infer_fields(features),
        "style": style or _default_style(geometry_type),
        "sourceCrs": "EPSG:4326",
        "visible": True,
        "opacity": 1,
        "zIndex": 0,
        "createdAt": now,
        "updatedAt": now,
        "editable": True,
    }


def build_project(
    name: str,
    layers: List[Dict[str, Any]],
    *,
    view: Optional[Dict[str, Any]] = None,
    basemap: str = "none",
    features_by_layer: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """构造 ProjectFile v1。

    ``layers`` 两种写法二选一：
    - 简式: [{"name": "...", "features": [...], "style"?}: ...]（自动补全 LayerModel）
    - 全式: 已是 LayerModel 的完整 dict（原样使用）
    """
    now = int(time.time() * 1000)
    resolved: List[Dict[str, Any]] = []
    for i, layer in enumerate(layers):
        if layer.get("kind") == "vector" and "id" in layer:
            resolved.append(layer)
        else:
            built = build_vector_layer(layer.get("name", "图层"), layer.get("features", []), layer.get("style"))
            built["zIndex"] = i
            resolved.append(built)
    return {
        "app": "spatial-harness",
        "version": 1,
        "id": _uid("proj"),
        "name": name,
        "createdAt": now,
        "updatedAt": now,
        "view": view,
        "basemap": basemap,
        "crs": "EPSG:3857",
        "layerOrder": [l["id"] for l in resolved],
        "layers": resolved,
    }


def write_project(project: Dict[str, Any], path: str) -> str:
    """把工程 JSON 写到磁盘（默认文件名 project.webgis.json）。"""
    if os.path.isdir(path):
        path = os.path.join(path, "project.webgis.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False)
    return path
