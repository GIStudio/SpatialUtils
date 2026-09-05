"""Plugin protocol.

Every SpatialUtils plugin is an instance (or subclass) of :class:`Plugin`.
Existing libraries are *not* rewritten; they are wrapped in adapters that
subclass :class:`Plugin` and forward :meth:`Plugin.run` to the library call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass(frozen=True)
class PluginInfo:
    """Immutable metadata describing a plugin instance."""

    name: str
    version: str = "0.0.0"
    category: str = "general"
    description: str = ""
    author: str = ""
    input_contract: Dict[str, str] = field(default_factory=dict)
    output_contract: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "category": self.category,
            "description": self.description,
            "author": self.author,
            "input_contract": dict(self.input_contract),
            "output_contract": dict(self.output_contract),
        }


class Plugin:
    """Base class for all plugins.

    Class attributes double as the plugin manifest; override them in
    subclasses. ``input_contract`` / ``output_contract`` map payload keys to
    contract type names understood by :mod:`spatialharness.core.contracts`
    (``table``, ``geodataframe``, ``series``, ``path``, ``any``).
    """

    name: str = "unnamed"
    version: str = "0.0.0"
    category: str = "general"
    description: str = ""
    author: str = ""
    input_contract: Dict[str, str] = {}
    output_contract: Dict[str, str] = {}

    def info(self) -> PluginInfo:
        return PluginInfo(
            name=self.name,
            version=self.version,
            category=self.category,
            description=self.description,
            author=self.author,
            input_contract=dict(self.input_contract),
            output_contract=dict(self.output_contract),
        )

    # -- lifecycle hooks (optional) --------------------------------------
    def setup(self, context: "Any") -> None:  # noqa: ANN401
        """Called once before the first run. Optional."""

    def teardown(self) -> None:
        """Called when the plugin is unregistered. Optional."""

    def run(self, data: Any = None, **params: Any) -> Any:  # noqa: ANN401
        """Execute the plugin. ``data`` is the standardized input payload;
        ``params`` are plugin-specific keyword arguments."""
        raise NotImplementedError(f"plugin {self.name!r} does not implement run()")


def plugin_from_function(
    func: Callable[..., Any],
    name: str,
    version: str = "0.0.0",
    category: str = "general",
    description: str = "",
    input_contract: Optional[Dict[str, str]] = None,
    output_contract: Optional[Dict[str, str]] = None,
) -> Plugin:
    """Wrap a plain function as a Plugin instance (quick-and-dirty adapters)."""

    contract_in = dict(input_contract or {})
    contract_out = dict(output_contract or {})

    class FunctionPlugin(Plugin):
        def run(self, data: Any = None, **params: Any) -> Any:  # noqa: ANN401
            kwargs = dict(params)
            if data is not None:
                kwargs.setdefault("data", data)
            return func(**kwargs)

    fp = FunctionPlugin()
    fp.name = name
    fp.version = version
    fp.category = category
    fp.description = description or (func.__doc__ or "").strip().split("\n")[0]
    fp.input_contract = contract_in
    fp.output_contract = contract_out
    return fp
