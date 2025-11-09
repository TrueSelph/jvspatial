"""Services module for jvspatial API.

This module contains service implementations for the API, including
endpoint registration, lifecycle management, and other core services.
"""

from jvspatial.api.services.discovery import PackageDiscoveryService

# Note: EndpointRegistryService moved to endpoints module
# from jvspatial.api.services.endpoint_registry import (
#     EndpointInfo,
#     EndpointRegistryService,
# )
# Note: FileStorageService moved to integrations/storage module
# from jvspatial.api.services.file_storage import FileStorageService
from jvspatial.api.services.lifecycle import LifecycleManager

# Note: MiddlewareManager moved to middleware module
# from jvspatial.api.services.middleware import MiddlewareManager

__all__ = [
    # "EndpointInfo",           # Moved to endpoints
    # "EndpointRegistryService", # Moved to endpoints
    # "FileStorageService",     # Moved to integrations/storage
    "LifecycleManager",
    # "MiddlewareManager",  # Moved to middleware module
    "PackageDiscoveryService",
]
