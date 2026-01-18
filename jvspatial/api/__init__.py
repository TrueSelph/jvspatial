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
from .decorators.deferred_registry import (
    clear_deferred_endpoints,
    flush_deferred_endpoints,
    get_deferred_endpoint_count,
    register_deferred_endpoint,
)
from .decorators.field import EndpointField, EndpointFieldInfo, endpoint_field
from .decorators.route import endpoint
from .endpoints.response import ResponseHelper, format_response
from .endpoints.router import BaseRouter, EndpointRouter
from .lambda_server import LambdaServer
from .server import Server, create_server

__all__ = [
    "Server",
    "LambdaServer",
    "ServerConfig",
    "create_server",
    "get_current_server",
    "set_current_server",
    "ServerContext",
    "endpoint",
    "BaseRouter",
    "EndpointRouter",
    "endpoint_field",
    "EndpointField",
    "EndpointFieldInfo",
    "format_response",
    "ResponseHelper",
    # Deferred registry utilities (for debugging and testing)
    "register_deferred_endpoint",
    "flush_deferred_endpoints",
    "get_deferred_endpoint_count",
    "clear_deferred_endpoints",
]
