"""Endpoint-related functionality for jvspatial API.

This module contains:
- Parameter model generation
- Field configuration
- Router implementation
"""

from ..parameters import ParameterModelFactory
from ..routing import EndpointRouter
from .decorators import EndpointField, EndpointFieldInfo, endpoint_field

__all__ = [
    "endpoint_field",
    "EndpointField",
    "EndpointFieldInfo",
    "ParameterModelFactory",
    "EndpointRouter",
]
