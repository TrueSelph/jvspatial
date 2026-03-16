"""Components module for jvspatial API.

This module provides focused, single-responsibility components that work together
to build the complete API functionality, following the new standard implementation.
"""

from .app_builder import AppBuilder
from .auth_middleware import AuthenticationMiddleware
from .endpoint_auth_resolver import EndpointAuthResolver
from .endpoint_manager import EndpointManager
from .error_handler import APIErrorHandler
from .path_matcher import PathMatcher

__all__ = [
    "AppBuilder",
    "AuthenticationMiddleware",
    "EndpointAuthResolver",
    "EndpointManager",
    "APIErrorHandler",
    "ErrorHandler",
    "PathMatcher",
]
