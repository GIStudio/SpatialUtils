from __future__ import annotations

import pytest

from spatialharness.core import PluginManager
from spatialharness.wire import (
    json_to_payload,
    payload_to_json,
    run_plugin_via_json,
    tool_description_for,
    tool_schema_for,
)

pd = pytest.importorskip("pandas")


def test_json_to_payload_records():
    df = json_to_payload([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_json_to_payload_geojson_properties():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": "n1", "v": 1}, "geometry": None},
            {"type": "Feature", "properties": {"name": "n2", "v": 2}, "geometry": None},
        ],
    }
    df = json_to_payload(fc)
    assert df["name"].tolist() == ["n1", "n2"]


def test_json_to_payload_passthrough():
    assert json_to_payload("D:/folder") == "D:/folder"
    assert json_to_payload(None) is None


def test_payload_to_json_dataframe():
    df = pd.DataFrame([{"x": 1}, {"x": 2}])
    out = payload_to_json(df)
    assert out["format"] == "records"
    assert out["rows"] == [{"x": 1}, {"x": 2}]


def test_payload_to_json_nested():
    out = payload_to_json({"metadata": pd.DataFrame([{"n": 1}]), "msg": "ok"})
    assert out["msg"] == "ok"
    assert out["metadata"]["rows"] == [{"n": 1}]


def test_payload_to_json_unserializable_falls_back_to_str():
    out = payload_to_json({"obj": object()})
    assert isinstance(out["obj"], str)


def test_tool_schema_contains_contract():
    mgr = PluginManager(extra_dirs=[], auto_load=False)
    schema = tool_schema_for(mgr.get("street_solar"))
    assert schema["type"] == "object"
    assert "folder=path" in schema["properties"]["data"]["description"]


def test_tool_description_contains_contracts():
    mgr = PluginManager(extra_dirs=[], auto_load=False)
    desc = tool_description_for(mgr.get("spatial_accessibility"))
    assert "data=table" in desc
    assert "accessibility=table" in desc


def test_run_plugin_via_json_roundtrip():
    mgr = PluginManager(extra_dirs=[], auto_load=True)  # 自动发现 ./plugins 的 hello
    out = run_plugin_via_json(mgr, "hello", None, {"who": "MCP"})
    assert out == {"message": "Hello, MCP! (SpatialHarness 插件系统工作正常)"}
