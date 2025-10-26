"""API module for jvspatial.

This module provides:
- Server implementation with FastAPI integration
- Authentication and authorization
- Response handling
- Endpoint configuration
- Error handling
"""

from .config import ServerConfig
from .context import ServerContext, get_current_server, set_current_server
from .decorators.route import (
    admin_endpoint,
    auth_endpoint,
    endpoint,
    webhook_endpoint,
)

# Note: EndpointField, EndpointFieldInfo, endpoint_field moved to endpoints module
# from .endpoints import EndpointField, EndpointFieldInfo, endpoint_field
# from .endpoints import ResponseHelper, format_response
# Note: Routing moved to endpoints module
# from .routing import (
#     BaseRouter,
#     EndpointRouter,
# )
from .server import Server, create_server

__all__ = [
    # Main exports
    "Server",
    "ServerConfig",
    "create_server",
    "get_current_server",
    "set_current_server",
    "ServerContext",
    "endpoint",
    "auth_endpoint",
    "webhook_endpoint",
    "admin_endpoint",
    # Core routers (for advanced usage)
    "BaseRouter",
    "EndpointRouter",
    # Field configuration
    "endpoint_field",
    "EndpointField",
    "EndpointFieldInfo",
    # Response handling
    "format_response",
    "ResponseHelper",
]
