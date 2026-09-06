from __future__ import annotations

import json

from spatialharness.authoring import build_project, build_vector_layer, write_project

FEATURES = [
    {"type": "Feature", "properties": {"name": "北京", "pop": 2189},
     "geometry": {"type": "Point", "coordinates": [116.4, 39.9]}},
    {"type": "Feature", "properties": {"name": "上海", "pop": 2487},
     "geometry": {"type": "Point", "coordinates": [121.5, 31.2]}},
]


def test_geometry_type_inference():
    assert build_vector_layer("a", FEATURES)["geometryType"] == "Point"
    poly = [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}]
    assert build_vector_layer("b", poly)["geometryType"] == "Polygon"
    mixed = FEATURES + poly
    assert build_vector_layer("c", mixed)["geometryType"] == "Mixed"
    assert build_vector_layer("d", [])["geometryType"] == "None"


def test_field_inference():
    fields = {f["name"]: f["type"] for f in build_vector_layer("a", FEATURES)["fields"]}
    assert fields["name"] == "string"
    assert fields["pop"] == "number"


def test_project_file_shape():
    project = build_project("测试", [{"name": "城市", "features": FEATURES}])
    assert project["app"] == "spatial-harness"
    assert project["version"] == 1
    assert project["crs"] == "EPSG:3857"
    assert len(project["layerOrder"]) == 1 == len(project["layers"])
    layer = project["layers"][0]
    assert layer["sourceCrs"] == "EPSG:4326"
    assert layer["style"]["symbol"]["kind"] == "simple"
    assert layer["editable"] is True
    # JSON 可序列化（Web 端 parseFromDisk 直接可用）
    json.dumps(project, ensure_ascii=False)


def test_write_project_dir_defaults_filename(tmp_path):
    path = write_project(build_project("p", []), str(tmp_path))
    assert path.endswith("project.webgis.json")
