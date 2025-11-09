"""Middleware for jvspatial API.

Consolidated middleware including authentication, error handling, and management.
"""

# Import what's available, skip what's not
__all__ = []

try:
    from .auth import AuthMiddleware, SessionMiddleware  # noqa: F401

    __all__.extend(["AuthMiddleware", "SessionMiddleware"])
except ImportError:
    pass

try:
    from .manager import MiddlewareManager  # noqa: F401

    __all__.append("MiddlewareManager")
except ImportError:
    pass

# error.py contains error_handlers functions, not a class
# Skip for now
