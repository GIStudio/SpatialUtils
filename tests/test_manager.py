from __future__ import annotations

import pytest

from spatialharness.core import (
    DuplicatePluginError,
    Plugin,
    PluginManager,
    PluginNotFoundError,
)


class UpperPlugin(Plugin):
    name = "upper"
    version = "9.9.9"
    category = "test"
    description = "把输入 dict 中的 value 变大写"
    input_contract = {"data": "table"}
    output_contract = {"out": "any"}

    def run(self, data=None, **params):
        return {"out": {k: str(v).upper() for k, v in data.items()}}


class FakeTable(dict):
    """duck-typed table-ish mapping for contract tests."""


@pytest.fixture()
def mgr():
    return PluginManager(extra_dirs=[], auto_load=False)


def test_builtins_registered(mgr):
    plugins = mgr.list_plugins()
    assert "spatial_accessibility" in plugins
    assert "street_solar" in plugins
    assert plugins["street_solar"].category == "streetview"


def test_register_and_run(mgr):
    mgr.register(UpperPlugin, source="test")
    result = mgr.run("upper", FakeTable(a="x"))
    assert result == {"out": {"a": "X"}}


def test_duplicate_name_rejected(mgr):
    mgr.register(UpperPlugin, source="test")
    with pytest.raises(DuplicatePluginError):
        mgr.register(UpperPlugin, source="test2")


def test_disable_enable(mgr):
    mgr.register(UpperPlugin)
    mgr.disable("upper")
    with pytest.raises(PluginNotFoundError):
        mgr.run("upper", FakeTable())
    mgr.enable("upper")
    assert mgr.is_enabled("upper")


def test_unknown_plugin(mgr):
    with pytest.raises(PluginNotFoundError):
        mgr.run("nope")


def test_unregister(mgr):
    mgr.register(UpperPlugin)
    mgr.unregister("upper")
    assert "upper" not in mgr.list_plugins()


def test_pipeline_chaining(mgr):
    class AddSuffix(Plugin):
        name = "add_suffix"

        def run(self, data=None, **params):
            return {"out": str(data["out"]) + "!"}

    mgr.register(UpperPlugin)
    mgr.register(AddSuffix)
    result = mgr.run_pipeline(
        [{"plugin": "upper"}, {"plugin": "add_suffix"}],
        FakeTable(a="x"),
    )
    assert result == {"out": "{'a': 'X'}!"}


def test_local_dir_discovery(tmp_path, mgr):
    plugin_file = tmp_path / "greet_plugin.py"
    plugin_file.write_text(
        "from spatialharness.core.plugin import Plugin\n"
        "class GreetPlugin(Plugin):\n"
        "    name = 'greet'\n"
        "    def run(self, data=None, **params):\n"
        "        return {'message': 'hi ' + params.get('who', 'world')}\n",
        encoding="utf-8",
    )
    loaded = mgr._discover_local([tmp_path])
    assert "greet" in loaded
    assert mgr.run("greet", who="GIS") == {"message": "hi GIS"}
