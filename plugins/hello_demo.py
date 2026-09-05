"""演示用本地插件：放入任意被扫描的 plugins/ 目录即自动注册。

用法::

    spatialutils list                      # 应出现 hello
    spatialutils run hello --param who=GIS
"""

from spatialutils.core.contracts import ANY
from spatialutils.core.plugin import Plugin


class HelloPlugin(Plugin):
    name = "hello"
    version = "0.0.1"
    category = "demo"
    description = "最小可运行示例插件：回显问候"
    input_contract = {"data": ANY}
    output_contract = {"message": ANY}

    def run(self, data=None, *, who: str = "world", **params):
        return {"message": f"Hello, {who}! (SpatialUtils 插件系统工作正常)"}
