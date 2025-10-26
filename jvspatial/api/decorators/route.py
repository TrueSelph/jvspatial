"""Route-level decorators for API endpoints.

This module provides decorators that control HTTP routing, authentication,
and methods. These decorators are applied to functions or classes that
handle HTTP requests.

Examples:
    @endpoint("/api/users", methods=["GET"])
    async def get_users():
        return {"users": [...]}

    @auth_endpoint("/api/admin", roles=["admin"])
    async def admin_panel():
        return {"admin": "dashboard"}
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from .route_config import EndpointConfig, EndpointDecorator, WebhookConfig


def endpoint(path: str, methods: Optional[List[str]] = None, **kwargs: Any) -> Callable:
    """Create a basic endpoint decorator.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods (defaults to ["GET"])
        **kwargs: Additional configuration options

    Returns:
        Decorator function
    """
    cfg = EndpointConfig(path=path, methods=methods or ["GET"], **kwargs)
    return EndpointDecorator.endpoint(cfg)


def auth_endpoint(
    path: str,
    methods: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    **kwargs: Any,
) -> Callable:
    """Create an authenticated endpoint decorator.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods (defaults to ["GET"])
        permissions: Required permissions
        roles: Required roles
        **kwargs: Additional configuration options

    Returns:
        Decorator function
    """
    cfg = EndpointConfig(
        path=path,
        methods=methods or ["GET"],
        auth_required=True,
        permissions=permissions or [],
        roles=roles or [],
        **kwargs,
    )
    return EndpointDecorator.endpoint(cfg)


def webhook_endpoint(
    path: str,
    methods: Optional[List[str]] = None,
    hmac_secret: Optional[str] = None,
    **kwargs: Any,
) -> Callable:
    """Create a webhook endpoint decorator.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods (defaults to ["POST"])
        hmac_secret: Optional HMAC secret for verification
        **kwargs: Additional configuration options

    Returns:
        Decorator function
    """
    wh = WebhookConfig(hmac_secret=hmac_secret)
    cfg = EndpointConfig(path=path, methods=methods or ["POST"], webhook=wh, **kwargs)
    return EndpointDecorator.endpoint(cfg)


def admin_endpoint(
    path: str, methods: Optional[List[str]] = None, **kwargs: Any
) -> Callable:
    """Create an admin-only endpoint decorator.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods (defaults to ["GET"])
        **kwargs: Additional configuration options

    Returns:
        Decorator function
    """
    return auth_endpoint(path, methods=methods, roles=["admin"], **kwargs)
