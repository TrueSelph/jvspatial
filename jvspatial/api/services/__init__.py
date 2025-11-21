"""Services module for jvspatial API.

This module contains service implementations for the API, including
endpoint registration, lifecycle management, and other core services.
"""

from jvspatial.api.services.discovery import EndpointDiscoveryService
from jvspatial.api.services.lifecycle import LifecycleManager

__all__ = [
    "LifecycleManager",
    "EndpointDiscoveryService",
]
