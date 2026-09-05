# SpatialUtils

**插件式的 GIS / 城市科学工具库** —— 轻量核心只做两件事：**插件管理**与**数据契约**；所有功能由插件提供，现有库不重写、以适配器方式接入。

> 核心理念：像 pytest 收集测试、napari 收集插件一样收集城市科学工具。
> 核心零第三方依赖（纯标准库），数据契约通过 duck-typing 校验，不强制 pandas/geopandas。

## 安装

```bash
pip install spatialutils                # 核心
pip install spatialutils[access]        # + SpatialAccessibility 适配器后端
pip install spatialutils[street]        # + StreetSolarTrack 适配器后端
pip install spatialutils[all]           # 全部后端
```

## 快速开始

### Python API

```python
from spatialutils import PluginManager

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
spatialutils list                                   # 列出插件
spatialutils show street_solar                      # 查看数据契约
spatialutils run street_solar --param folder=./photos --param report=true
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
from spatialutils.core.plugin import Plugin

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
from spatialutils.core import plugin_from_function
plugin = plugin_from_function(my_func, name="my_tool",
                              input_contract={"data": "table"})
mgr.register(plugin)
```

### 发布为可安装插件（entry points）

在你的 `pyproject.toml` 里：

```toml
[project.entry-points."spatialutils.plugins"]
my-tool = "my_package.plugin:MyPlugin"
```

`pip install` 后即被所有 SpatialUtils 用户自动发现。

### 本地即插即用

把 `*.py` 丢进 `~/.spatialutils/plugins/` 或项目下 `plugins/` 目录即可，
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
| `spatial_accessibility`| SpatialAccessibility 0.0.13 | `pip install spatialutils[access]` |
| `street_solar`         | StreetSolarTrack 0.0.10     | `pip install spatialutils[street]` |

后端库缺失时，插件在 `run()` 时才报错并给出 pip 提示（懒导入，核心保持轻量）。

## 开发

```bash
git clone https://github.com/GIStudio/SpatialUtils.git
cd SpatialUtils
pip install -e .[dev]
pytest
```

## License

MIT © GIStudio / Shiqi Wang
