"""Adapter wrapping the existing SpatialAccessibility library (no rewrite).

Upstream: https://github.com/wsqstar/SpatialAccessibility  (pip: SpatialAccessibility)
"""

from __future__ import annotations

from typing import Any, Dict

from ..core.contracts import TABLE
from ..core.errors import PluginLoadError
from ..core.plugin import Plugin


class SpatialAccessibilityPlugin(Plugin):
    name = "spatial_accessibility"
    version = "0.0.13"  # wrapped upstream version
    category = "accessibility"
    description = "空间可达性计算（Gravity/FCA 模型），包装 SpatialAccessibility 库"
    author = "Shiqi Wang"
    input_contract = {"data": TABLE}  # OD 矩阵 DataFrame
    output_contract = {
        "accessibility": TABLE,  # 各 O 点可达性得分
        "summary": TABLE,  # 模型参数与统计摘要
    }

    _PIP_HINT = "pip install SpatialAccessibility  (或 pip install spatialharness[access])"

    def run(self, data: Any = None, *, method: str = "gravity", **params: Any) -> Dict[str, Any]:
        try:
            from SpatialAccessibility import (
                calculate_accessibility,
                calculate_accessibility_fca,
            )
        except ImportError as exc:
            raise PluginLoadError(f"SpatialAccessibility 未安装: {exc}\n  → {self._PIP_HINT}") from exc

        params.setdefault("print_out", False)

        if method == "fca":
            origins = params.pop("origins", None)
            destinations = params.pop("destinations", None)
            if origins is None or destinations is None:
                raise ValueError("FCA 模式需要 params: origins / destinations 两个 DataFrame")
            result = calculate_accessibility_fca(origins, destinations, **params)
            # upstream returns (accessibility_df, summary_df) as well
            accessibility, summary = self._unpack(result)
        else:
            if data is None:
                raise ValueError("gravity 模式需要 data: OD 矩阵 DataFrame (见库文档)")
            result = calculate_accessibility(data, **params)
            accessibility, summary = self._unpack(result)

        return {"accessibility": accessibility, "summary": summary}

    @staticmethod
    def _unpack(result: Any) -> tuple[Any, Any]:
        if isinstance(result, tuple) and len(result) == 2:
            return result[0], result[1]
        return result, None
