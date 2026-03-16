"""Authentication configuration for jvspatial API.

This module re-exports the unified AuthConfig from config_groups.
The middleware and auth components use this single configuration model.
"""

from jvspatial.api.config_groups import AuthConfig

__all__ = ["AuthConfig"]
