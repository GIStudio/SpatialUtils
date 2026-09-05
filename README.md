# SpatialHarness

**插件式的 GIS / 城市科学工具库** —— 轻量核心只做两件事：**插件管理**与**数据契约**；所有功能由插件提供，现有库不重写、以适配器方式接入。

> 核心理念：像 pytest 收集测试、napari 收集插件一样收集城市科学工具。
> 核心零第三方依赖（纯标准库），数据契约通过 duck-typing 校验，不强制 pandas/geopandas。

## 安装

```bash
pip install spatialharness                # 核心
pip install spatialharness[access]        # + SpatialAccessibility 适配器后端
pip install spatialharness[street]        # + StreetSolarTrack 适配器后端
pip install spatialharness[all]           # 全部后端
```

## 快速开始

### Python API

```python
from spatialharness import PluginManager

mgr = PluginManager()
print(mgr.list_plugins())
# {'spatial_accessibility': ..., 'street_solar': ...}

# 街景元数据（包装 StreetSolarTrack，不改变原库用法）
result = mgr.run("street_solar", folder="data/street_views", report=True)
result["metadata"].head()

# 空间可达性（包装 SpatialAccessibility 0.0.13）
result = mgr.run("spatial_accessibility", od_matrix_df, AccModel="Gravity", beta=1)
result["accessibility"].head()
```

### CLI

```bash
spatialharness list                                   # 列出插件
spatialharness show street_solar                      # 查看数据契约
spatialharness run street_solar --param folder=./photos --param report=true
```

### 管理插件

```python
mgr.disable("street_solar")   # 禁用
mgr.enable("street_solar")    # 启用
mgr.source_of("street_solar") # 来源: builtin / entrypoint:xxx / local:path
```

## 架构

```
┌─────────────────────────────────────────────┐
│  接口层   Python API  ·  CLI                 │
├─────────────────────────────────────────────┤
│  核心层   PluginManager · Plugin 协议        │
│           数据契约 (duck-typing 校验)         │
│           —— 纯标准库，零第三方依赖 ——         │
├──────────┬──────────────┬───────────────────┤
│ 插件层    │ builtin 适配器│ entry points 插件 │ 本地 plugins/ 目录
│          │ (包装现有库)  │ (第三方 pip 包)    │ (实验性脚本)
└──────────┴──────────────┴───────────────────┘
```

## 数据契约

插件声明输入/输出契约，核心在运行前后校验（duck-typing，不强制依赖）：

| 类型            | 判定                                        |
|-----------------|---------------------------------------------|
| `table`         | 有 `columns` + `iloc`（pandas DataFrame 满足）|
| `geodataframe`  | table 且有 `geometry`（geopandas）           |
| `series`        | 有 `iloc` 无 `columns`                       |
| `path`          | `str` / `os.PathLike`                        |
| `any`           | 不检查                                       |

## 编写插件

### 方式一：类（推荐）

```python
from spatialharness.core.plugin import Plugin

class MyPlugin(Plugin):
    name = "my_tool"
    version = "0.1.0"
    category = "analysis"
    input_contract = {"data": "table"}
    output_contract = {"result": "table"}

    def run(self, data=None, **params):
        ...  # 调用你的算法
        return {"result": df}
```

### 方式二：包装现成函数

```python
from spatialharness.core import plugin_from_function
plugin = plugin_from_function(my_func, name="my_tool",
                              input_contract={"data": "table"})
mgr.register(plugin)
```

### 发布为可安装插件（entry points）

在你的 `pyproject.toml` 里：

```toml
[project.entry-points."spatialharness.plugins"]
my-tool = "my_package.plugin:MyPlugin"
```

`pip install` 后即被所有 SpatialUtils 用户自动发现。

### 本地即插即用

把 `*.py` 丢进 `~/.spatialharness/plugins/` 或项目下 `plugins/` 目录即可，
参见本仓库 [`plugins/hello_demo.py`](plugins/hello_demo.py)。

## 插件流水线（pipeline）

```python
mgr.run_pipeline([
    {"plugin": "street_solar", "params": {"folder": "photos"}},
    {"plugin": "spatial_accessibility", "input_key": "metadata"},
])
```

每个步骤的输出自动作为下一步输入；`input_key` 可从上一步结果字典中选键。

## 内置适配器（现有库不重写）

| 插件名                 | 包装的库              | 后端安装                |
|------------------------|------------------------|-------------------------|
| `spatial_accessibility`| SpatialAccessibility 0.0.13 | `pip install spatialharness[access]` |
| `street_solar`         | StreetSolarTrack 0.0.10     | `pip install spatialharness[street]` |

后端库缺失时，插件在 `run()` 时才报错并给出 pip 提示（懒导入，核心保持轻量）。

## 开发

```bash
git clone https://github.com/GIStudio/SpatialUtils.git
cd SpatialUtils
pip install -e .[dev]
pytest
```

## Handoff / 交接说明

> 面向后续维护者（人或 AI 会话）的现状速览。最后更新：2026-09-05。

### 命名沿革（重要，避免混淆）

- **仓库名** `SpatialUtils`（github.com/GIStudio/SpatialUtils），**包名** `spatialharness`——两者有意不同。
- 原包名 `spatialutils` 被 PyPI 以"与既有 `spatial-utils` 过于相似"为由拒绝，2026-09-05 全局重命名：导入包、CLI 命令、entry-points 组（`spatialharness.plugins`）、本地插件目录（`~/.spatialharness/plugins/`）。
- `SpatialAccessibility` 与 `StreetSolarTrack` 是**独立发布的第三方风格库**，本库只做适配器包装，不改动它们。

### 当前状态（v0.1.0，已发布 PyPI）

- 核心（纯标准库零依赖）：PluginManager（entry points + 本地目录双发现、启停）、Plugin 协议、duck-typing 数据契约、`run_pipeline` 链式调用。
- 内置适配器：`spatial_accessibility`（SpatialAccessibility 0.0.13）、`street_solar`（StreetSolarTrack 0.0.10），后端懒导入，缺失时 `run()` 才报错并给 pip 提示。
- 三个包均已在 PyPI：spatialharness 0.1.0 / SpatialAccessibility 0.0.13 / StreetSolarTrack 0.0.10。
- 测试：24 个，`pytest` 全过（Windows / Python 3.12 验证）。

### 代码地图

| 路径 | 职责 |
|---|---|
| `src/spatialharness/core/plugin.py` | Plugin 基类与协议、PluginInfo、`plugin_from_function` |
| `src/spatialharness/core/manager.py` | 发现 / 注册 / 启停 / `run` / `run_pipeline` |
| `src/spatialharness/core/contracts.py` | 契约类型判定（duck-typing）与校验 |
| `src/spatialharness/core/errors.py` | 异常体系 |
| `src/spatialharness/adapters/` | 两个内置适配器，汇总于 `BUILTIN_ADAPTERS` |
| `src/spatialharness/cli.py` | CLI：list / show / run / enable / disable |
| `plugins/hello_demo.py` | 本地即插即用示例插件 |
| `tests/` | 24 个测试（manager / contracts / cli / adapters） |

### 如何扩展

- **新内置适配器**：在 `adapters/` 加 Plugin 子类并注册进 `BUILTIN_ADAPTERS`（参考 `street_solar.py`）。
- **第三方插件**：独立 Python 包，在自己的 `pyproject.toml` 声明 `[project.entry-points."spatialharness.plugins"]`。
- **实验性插件**：`*.py` 丢进 `~/.spatialharness/plugins/` 或项目 `plugins/` 目录。

### 发布流程

1. 同步版本号：`pyproject.toml` 的 `version` 与 `VERSION` 文件。
2. `python -m build` 产出 `dist/`，`python -m twine check dist/*` 校验。
3. `python -m twine upload dist/*`（凭据由维护者自行配置，勿写入仓库）。
4. git 打 tag 并推送。

### 已知边界 / 下一步

- 尚无 CI（建议：push 时跑 pytest + build 冒烟，参考 GIStudioNote 的 Actions 配置）。
- 契约只校验数据形态，不做数值范围 / CRS 一致性校验。
- `hello` 插件仅作演示，发布正式版前可移入 examples。
- 远期：CitySense 分析流程固化为 perception 类插件；接入 ZenSVI 街景下载能力。

## License

MIT © GIStudio / Shiqi Wang
