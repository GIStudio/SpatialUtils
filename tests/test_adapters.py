from __future__ import annotations

import pytest

from spatialutils.core import PluginLoadError, PluginManager


@pytest.fixture()
def mgr():
    return PluginManager(extra_dirs=[], auto_load=False)


def test_accessibility_plugin_info(mgr):
    info = mgr.list_plugins()["spatial_accessibility"]
    assert info.input_contract == {"data": "table"}
    assert info.output_contract["accessibility"] == "table"


def test_accessibility_lazy_import_error(mgr):
    pytest.importorskip("pandas")
    if _lib_available():
        pytest.skip("SpatialAccessibility 已安装，无法在本机测未安装分支")
    with pytest.raises(PluginLoadError, match="pip install"):
        mgr.run("spatial_accessibility", None)


def _lib_available() -> bool:
    try:
        import SpatialAccessibility  # noqa: F401

        return True
    except ImportError:
        return False


def test_street_solar_real_run(mgr, tmp_path):
    pytest.importorskip("PIL")
    pytest.importorskip("pandas")
    if not _street_lib_available():
        pytest.skip("StreetSolarTrack 未安装")
    from PIL import Image

    for i in range(3):
        Image.new("RGB", (64, 48)).save(tmp_path / f"img_{i}.jpg")

    result = mgr.run("street_solar", folder=str(tmp_path), report=True)
    assert len(result["metadata"]) == 3
    assert (tmp_path / "metadata_report.html").exists()


def _street_lib_available() -> bool:
    try:
        import StreetSolarTrack  # noqa: F401

        return True
    except ImportError:
        return False


def test_street_solar_missing_folder(mgr):
    with pytest.raises(ValueError, match="folder"):
        mgr.run("street_solar")


def test_contract_violation_caught(mgr):
    # spatial_accessibility 契约要求 table，传入 path 字符串应被拦截
    if _lib_available():
        pytest.skip("环境已装 SpatialAccessibility（错误类型不同）")
    with pytest.raises(Exception):
        mgr.run("spatial_accessibility", "D:/not_a_table.csv")
