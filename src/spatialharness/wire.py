"""Wire layer: JSON ⇄ 插件数据契约 的双向转换。

MCP / HTTP 桥收到的是纯 JSON；插件的 table/geodataframe 契约期望
pandas / geopandas 对象。本模块负责转换，pandas 与 geopandas 都是
可选依赖（缺失时给出带 pip 提示的明确错误），核心保持零依赖。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

_PANDAS_HINT = "pip install pandas  (或 pip install spatialharness[access])"
_GEOPANDAS_HINT = "pip install geopandas"


def _pandas():
    try:
        import pandas

        return pandas
    except ImportError as exc:  # pragma: no cover - 环境相关
        raise RuntimeError(f"该数据需要 pandas: {exc}\n  → {_PANDAS_HINT}") from exc


# ---------------------------------------------------------------------------
# 入向: JSON → 契约 payload
# ---------------------------------------------------------------------------

def json_to_payload(data: Any) -> Any:
    """把 JSON 值转成最接近插件契约的对象。

    * list[dict]                    → DataFrame
    * GeoJSON FeatureCollection     → GeoDataFrame(装了 geopandas) / DataFrame(仅属性)
    * GeoJSON Feature               → 单行，同上
    * 其它                           → 原样返回（duck-typing 契约自行判断）
    """
    if isinstance(data, list) and data and all(isinstance(r, dict) for r in data):
        return _pandas().DataFrame(data)
    if isinstance(data, dict) and data.get("type") in ("FeatureCollection", "Feature"):
        return _geojson_to_frame(data)
    return data


def _geojson_to_frame(geojson: Dict[str, Any]):
    pd = _pandas()
    features = (
        geojson.get("features", [])
        if geojson.get("type") == "FeatureCollection"
        else [geojson]
    )
    rows = []
    geoms = []
    for f in features:
        props = dict(f.get("properties") or {})
        rows.append(props)
        geoms.append(f.get("geometry"))
    df = pd.DataFrame(rows)
    if not geoms or all(g is None for g in geoms):
        return df
    try:
        import geopandas as gpd
        from shapely.geometry import shape
    except ImportError:
        return df  # 无 geopandas: 退化为属性表
    return gpd.GeoDataFrame(df, geometry=[shape(g) if g else None for g in geoms])


# ---------------------------------------------------------------------------
# 出向: 结果 → 可 JSON 序列化结构
# ---------------------------------------------------------------------------

def payload_to_json(value: Any) -> Any:
    """把插件返回值序列化为 JSON 友好结构。

    * GeoDataFrame → GeoJSON FeatureCollection
    * DataFrame    → {"format": "records", "rows": [...]}
    * Series       → list
    * 其它         → 原样（不可序列化的退化为 str）
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {k: payload_to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [payload_to_json(v) for v in value]
    if hasattr(value, "columns") and hasattr(value, "iloc"):
        return _frame_to_json(value)
    if hasattr(value, "iloc"):  # Series
        return [_jsonify(v) for v in value.tolist()]
    return _jsonify(value)


def _frame_to_json(frame: Any) -> Any:
    # GeoDataFrame: 优先 GeoJSON（与 Web 端原生格式对齐）
    if hasattr(frame, "geometry") and frame.geometry is not None:
        try:
            fc = json.loads(frame.to_json(drop_id=True))
            fc["format"] = "geojson"
            return fc
        except Exception:  # noqa: BLE001 - 退化路径
            pass
    rows = frame.where(frame.notna(), None).to_dict(orient="records")
    return {"format": "records", "columns": [str(c) for c in frame.columns], "rows": rows}


def _jsonify(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# 工具 schema 生成（MCP / HTTP 桥共用）
# ---------------------------------------------------------------------------

def tool_schema_for(plugin: Any) -> Dict[str, Any]:
    """由插件 manifest 生成 JSON Schema 输入描述。"""
    contract = getattr(plugin, "input_contract", None) or {}
    data_desc = (
        "插件标准输入数据；类型 "
        + ", ".join(f"{k}={v}" for k, v in contract.items())
        + "。支持 list[记录] 或 GeoJSON FeatureCollection（自动转 DataFrame）"
        if contract
        else "插件数据（本插件未声明输入契约）"
    )
    return {
        "type": "object",
        "properties": {
            "data": {"type": ["object", "array"], "description": data_desc},
            "params": {
                "type": "object",
                "additionalProperties": True,
                "description": "插件特有参数（透传给 run）",
            },
        },
        "required": [],
    }


def tool_description_for(plugin: Any) -> str:
    info = plugin.info()
    lines = [info.description or info.name]
    if info.input_contract:
        lines.append("输入契约: " + ", ".join(f"{k}={v}" for k, v in info.input_contract.items()))
    if info.output_contract:
        lines.append("输出契约: " + ", ".join(f"{k}={v}" for k, v in info.output_contract.items()))
    lines.append(f"类别: {info.category} | 版本: {info.version}")
    return "\n".join(lines)


def run_plugin_via_json(manager: Any, name: str, data: Any, params: Optional[Dict[str, Any]] = None) -> Any:
    """桥接入口: JSON 进 → manager.run → JSON 出。"""
    result = manager.run(name, json_to_payload(data), **(params or {}))
    return payload_to_json(result)
