"""SpatialUtils: a lightweight plugin-based toolkit for GIS and urban science.

The core does plugin management and data contracts only; all functionality
ships as plugins (built-in adapters wrap our existing libraries).

Quick start::

    from spatialharness import PluginManager

    mgr = PluginManager()
    print(mgr.list_plugins())
    result = mgr.run("street_solar", folder="data/street_views")
"""

from .core import (
    ContractError,
    Plugin,
    PluginInfo,
    PluginManager,
    plugin_from_function,
)
from .version import __version__

__author__ = "Shiqi Wang"

__all__ = [
    "ContractError",
    "Plugin",
    "PluginInfo",
    "PluginManager",
    "plugin_from_function",
    "__version__",
]
