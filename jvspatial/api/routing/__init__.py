"""Core routing implementations for the jvspatial API.

This module contains the core router implementations:
- Base router with common functionality
- Endpoint router for Walker-based endpoints

Note: Auth, webhook, and scheduler routing is handled by decorators
in their respective feature packages (auth/, webhook/, scheduler/).
"""

from .base import BaseRouter
from .endpoint import EndpointRouter

__all__ = [
    "BaseRouter",
    "EndpointRouter",
]
