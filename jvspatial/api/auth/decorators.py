"""Authentication decorators for JVspatial API endpoints.

This module provides authentication decorators that can be used to secure
API endpoints with various authentication mechanisms.
"""

from __future__ import annotations

from jvspatial.api.decorators.route import admin_endpoint, auth_endpoint

__all__ = [
    "auth_endpoint",
    "admin_endpoint",
]
