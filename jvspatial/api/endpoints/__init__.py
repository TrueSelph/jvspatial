"""Endpoint management for jvspatial API.

This module provides all endpoint-related functionality including:
- Response handling (response types, formatting, helpers)
- Routing (Walker and function endpoints)
- Parameter model generation
- Endpoint registry
"""

# Route decorators (for convenience, also available from api.decorators)
from ..decorators.route import endpoint

# Parameter models
from .factory import EndpointParameterModel, ParameterModelFactory

# Registry
from .registry import EndpointInfo, EndpointRegistryService, EndpointType

# Response handling
from .response import (
    APIResponse,
    EndpointResponse,
    ErrorResponse,
    ResponseHelper,
    SuccessResponse,
    create_endpoint_helper,
    format_response,
)

# Routing
from .router import AuthEndpoint, BaseRouter, EndpointRouter

__all__ = [
    # Route decorators
    "endpoint",
    # Response types
    "APIResponse",
    "SuccessResponse",
    "ErrorResponse",
    # Response utilities
    "format_response",
    "EndpointResponse",
    "ResponseHelper",
    "create_endpoint_helper",
    # Routing
    "BaseRouter",
    "EndpointRouter",
    "AuthEndpoint",
    # Parameter models
    "ParameterModelFactory",
    "EndpointParameterModel",
    # Registry
    "EndpointRegistryService",
    "EndpointInfo",
    "EndpointType",
]
