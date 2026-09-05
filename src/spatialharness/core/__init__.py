"""Core: plugin protocol, data contracts and the plugin manager."""

from .contracts import (
    ANY,
    GEODATAFRAME,
    PATH,
    SERIES,
    TABLE,
    describe_payload,
    enforce_payload,
    validate_payload,
)
from .errors import (
    ContractError,
    DuplicatePluginError,
    PluginLoadError,
    PluginNotFoundError,
    SpatialUtilsError,
)
from .manager import (
    ENTRY_POINT_GROUP,
    USER_PLUGIN_DIR,
    PluginContext,
    PluginManager,
)
from .plugin import Plugin, PluginInfo, plugin_from_function

__all__ = [
    "ANY",
    "GEODATAFRAME",
    "PATH",
    "SERIES",
    "TABLE",
    "ContractError",
    "describe_payload",
    "DuplicatePluginError",
    "enforce_payload",
    "ENTRY_POINT_GROUP",
    "Plugin",
    "PluginContext",
    "PluginInfo",
    "PluginLoadError",
    "PluginManager",
    "PluginNotFoundError",
    "SpatialUtilsError",
    "USER_PLUGIN_DIR",
    "validate_payload",
    "plugin_from_function",
]
