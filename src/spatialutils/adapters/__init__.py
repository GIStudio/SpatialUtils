"""Built-in adapters: existing libraries wrapped as plugins (no rewrite)."""

from .spatial_access import SpatialAccessibilityPlugin
from .street_solar import StreetSolarTrackPlugin

BUILTIN_ADAPTERS = [SpatialAccessibilityPlugin, StreetSolarTrackPlugin]

__all__ = ["BUILTIN_ADAPTERS", "SpatialAccessibilityPlugin", "StreetSolarTrackPlugin"]
