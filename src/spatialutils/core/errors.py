"""SpatialUtils core exceptions."""


class SpatialUtilsError(Exception):
    """Base error for all SpatialUtils failures."""


class PluginNotFoundError(SpatialUtilsError):
    """Raised when a plugin name is not registered or is disabled."""


class PluginLoadError(SpatialUtilsError):
    """Raised when a plugin (or its wrapped library) cannot be imported."""


class DuplicatePluginError(SpatialUtilsError):
    """Raised when two plugins claim the same name."""


class ContractError(SpatialUtilsError):
    """Raised when input/output data violates a plugin's data contract."""
