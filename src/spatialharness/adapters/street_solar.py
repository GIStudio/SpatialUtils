"""Adapter wrapping the existing StreetSolarTrack library (no rewrite).

Upstream: https://github.com/GIStudio/StreetSolarTrack  (pip: StreetSolarTrack)
"""

from __future__ import annotations

from typing import Any, Dict

from ..core.contracts import PATH, TABLE
from ..core.errors import PluginLoadError
from ..core.plugin import Plugin


class StreetSolarTrackPlugin(Plugin):
    name = "street_solar"
    version = "0.0.10"  # wrapped upstream version
    category = "streetview"
    description = "街景图像元数据批量读取与报告生成，包装 StreetSolarTrack 库"
    author = "Shiqi Wang"
    input_contract = {"folder": PATH}  # 街景图像文件夹
    output_contract = {"metadata": TABLE}  # 每张图的元数据表

    _PIP_HINT = "pip install StreetSolarTrack  (或 pip install spatialharness[street])"

    def run(self, data: Any = None, *, folder: Any = None, report: bool = False, **params: Any) -> Dict[str, Any]:
        folder = folder if folder is not None else data
        if folder is None:
            raise ValueError("需要 folder: 街景图像所在目录 (str/Path)")

        try:
            from StreetSolarTrack.utils.load_metadata import (
                load_folder,
                load_images_metadata,
            )
        except ImportError as exc:
            raise PluginLoadError(f"StreetSolarTrack 未安装: {exc}\n  → {self._PIP_HINT}") from exc

        if report:
            # 同时在 folder 下生成 metadata_report.html
            df = load_images_metadata(str(folder))
        else:
            df = load_folder(str(folder))
        return {"metadata": df}
