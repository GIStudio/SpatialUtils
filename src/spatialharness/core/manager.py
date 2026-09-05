"""Plugin manager: discovery, registration, lifecycle and execution.

Two discovery mechanisms:

1. **Entry points** – third-party packages declare plugins under the
   ``spatialharness.plugins`` group in their own ``pyproject.toml``::

       [project.entry-points."spatialharness.plugins"]
       my-plugin = "my_package.plugin:MyPlugin"

   The entry point may resolve to a :class:`~spatialharness.core.plugin.Plugin`
   subclass, an instance, or a zero-argument factory returning either.

2. **Local plugin directories** – any ``*.py`` file dropped into
   ``~/.spatialharness/plugins/`` or ``./plugins/`` is imported and every
   ``Plugin`` subclass found in it is registered. Ideal for experimental code.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from .contracts import enforce_payload, validate_payload
from .errors import DuplicatePluginError, PluginLoadError, PluginNotFoundError
from .plugin import Plugin, PluginInfo

LOGGER = logging.getLogger("spatialharness")

ENTRY_POINT_GROUP = "spatialharness.plugins"
USER_PLUGIN_DIR = Path.home() / ".spatialharness" / "plugins"
PROJECT_PLUGIN_DIR = Path.cwd() / "plugins"

PluginSource = Union[Plugin, type]


def _instantiate(source: PluginSource) -> Plugin:
    plugin = source() if isinstance(source, type) else source
    if not isinstance(plugin, Plugin):
        raise PluginLoadError(
            f"entry point resolved to {type(plugin)!r}, expected a Plugin instance/class"
        )
    return plugin


class PluginContext:
    """Runtime context handed to plugins via ``setup``; carries a logger and
    a scratch dict for cross-plugin state (pipeline chaining)."""

    def __init__(self) -> None:
        self.logger = LOGGER
        self.shared: Dict[str, Any] = {}

    def __setitem__(self, key: str, value: Any) -> None:
        self.shared[key] = value

    def __getitem__(self, key: str) -> Any:
        return self.shared[key]


class PluginManager:
    def __init__(
        self,
        extra_dirs: Optional[Iterable[Path]] = None,
        *,
        auto_load: bool = True,
        include_builtins: bool = True,
    ) -> None:
        self._plugins: Dict[str, Plugin] = {}
        self._enabled: Dict[str, bool] = {}
        self._sources: Dict[str, str] = {}
        self._context = PluginContext()
        self._dirs: List[Path] = [USER_PLUGIN_DIR, PROJECT_PLUGIN_DIR]
        if extra_dirs:
            self._dirs = list(extra_dirs) + self._dirs
        if include_builtins:
            self._register_builtins()
        if auto_load:
            self.discover()

    # -- registration ----------------------------------------------------
    def register(self, plugin: PluginSource, *, enabled: bool = True, source: str = "manual") -> PluginInfo:
        if isinstance(plugin, type):
            plugin = plugin()
        if plugin.name in self._plugins:
            raise DuplicatePluginError(
                f"plugin {plugin.name!r} already registered from {self._sources[plugin.name]!r}"
            )
        self._plugins[plugin.name] = plugin
        self._enabled[plugin.name] = enabled
        self._sources[plugin.name] = source
        plugin.setup(self._context)
        return plugin.info()

    def unregister(self, name: str) -> None:
        plugin = self._require(name)
        plugin.teardown()
        del self._plugins[name]
        del self._enabled[name]
        del self._sources[name]

    def _register_builtins(self) -> None:
        """Register the adapters wrapping our existing libraries."""
        from ..adapters import BUILTIN_ADAPTERS

        for adapter in BUILTIN_ADAPTERS:
            self.register(adapter(), enabled=True, source="builtin")

    # -- discovery ---------------------------------------------------------
    def discover(self, dirs: Optional[Iterable[Path]] = None) -> List[str]:
        """Scan entry points + plugin directories; return registered names."""
        loaded: List[str] = []
        for name in self._discover_entry_points():
            loaded.append(name)
        for name in self._discover_local(dirs or self._dirs):
            loaded.append(name)
        return loaded

    def _discover_entry_points(self) -> List[str]:
        loaded: List[str] = []
        try:
            from importlib.metadata import entry_points
        except ImportError:  # pragma: no cover - Python < 3.8
            return loaded
        try:
            eps = entry_points().select(group=ENTRY_POINT_GROUP)  # py3.10+
        except TypeError:  # py3.8/3.9 dict-like API
            eps = entry_points().get(ENTRY_POINT_GROUP, [])
        for ep in eps:
            try:
                obj = ep.load()
                info = self.register(_instantiate(obj), source=f"entrypoint:{ep.name}")
                loaded.append(info.name)
                LOGGER.debug("loaded entry-point plugin %s", info.name)
            except DuplicatePluginError:
                LOGGER.debug("entry-point plugin %s already registered", ep.name)
            except Exception as exc:  # noqa: BLE001 - one bad plugin must not kill the rest
                LOGGER.warning("failed to load entry-point plugin %s: %s", ep.name, exc)
        return loaded

    def _discover_local(self, dirs: Iterable[Path]) -> List[str]:
        loaded: List[str] = []
        seen_modules: set[str] = set()
        for directory in dirs:
            directory = Path(directory)
            if not directory.is_dir():
                continue
            for pyfile in sorted(directory.glob("*.py")):
                if pyfile.name.startswith("_"):
                    continue
                modname = f"spatialharness_local_{pyfile.stem}"
                if modname in seen_modules:
                    continue
                seen_modules.add(modname)
                try:
                    spec = importlib.util.spec_from_file_location(modname, pyfile)
                    if spec is None or spec.loader is None:
                        raise PluginLoadError(f"cannot import {pyfile}")
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[modname] = module
                    spec.loader.exec_module(module)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("failed to import plugin file %s: %s", pyfile, exc)
                    continue
                for attr in vars(module).values():
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, Plugin)
                        and attr is not Plugin
                        and getattr(attr, "name", "unnamed") != "unnamed"
                        and attr.__module__ == modname
                    ):
                        try:
                            info = self.register(attr, source=f"local:{pyfile}")
                            loaded.append(info.name)
                        except DuplicatePluginError:
                            pass
        return loaded

    # -- queries -----------------------------------------------------------
    def get(self, name: str) -> Plugin:
        return self._require(name)

    def _require(self, name: str) -> Plugin:
        if name not in self._plugins:
            raise PluginNotFoundError(
                f"plugin {name!r} not found; registered: {sorted(self._plugins)}"
            )
        if not self._enabled.get(name, False):
            raise PluginNotFoundError(f"plugin {name!r} is disabled")
        return self._plugins[name]

    def list_plugins(self, *, only_enabled: bool = False) -> Dict[str, PluginInfo]:
        return {
            name: plugin.info()
            for name, plugin in sorted(self._plugins.items())
            if not only_enabled or self._enabled.get(name)
        }

    def is_enabled(self, name: str) -> bool:
        return name in self._plugins and bool(self._enabled.get(name))

    def enable(self, name: str) -> None:
        if name not in self._plugins:
            raise PluginNotFoundError(f"plugin {name!r} not found")
        self._enabled[name] = True

    def disable(self, name: str) -> None:
        if name not in self._plugins:
            raise PluginNotFoundError(f"plugin {name!r} not found")
        self._enabled[name] = False

    def source_of(self, name: str) -> str:
        if name not in self._plugins:
            raise PluginNotFoundError(f"plugin {name!r} not found")
        return self._sources[name]

    # -- execution -----------------------------------------------------------
    def run(self, name: str, data: Any = None, **params: Any) -> Any:
        """Validate ``data`` against the plugin's input contract, execute,
        then validate the result against its output contract (non-strict:
        only declared keys that *are* present get type-checked)."""
        plugin = self._require(name)
        errors = validate_payload(data, plugin.input_contract, strict=False, label=f"{name} input")
        if errors:
            from .errors import ContractError

            raise ContractError("; ".join(errors))
        result = plugin.run(data, **params)
        errors = validate_payload(result, plugin.output_contract, strict=False, label=f"{name} output")
        if errors:
            from .errors import ContractError

            raise ContractError("; ".join(errors))
        return result

    # -- pipelines -----------------------------------------------------------
    def run_pipeline(self, steps: Iterable[Dict[str, Any]], data: Any = None) -> Any:
        """Chain plugins: each step is ``{"plugin": name, "params": {...}}``;
        a step may select its input from the previous result with
        ``{"plugin": name, "input_key": "accessibility"}``."""
        current = data
        for i, step in enumerate(steps, start=1):
            name = step["plugin"]
            params = step.get("params", {})
            input_key = step.get("input_key")
            payload = current
            if input_key is not None and isinstance(current, dict):
                payload = current[input_key]
            current = self.run(name, payload, **params)
            LOGGER.info("pipeline step %d (%s) done", i, name)
        return current

    @property
    def context(self) -> PluginContext:
        return self._context
