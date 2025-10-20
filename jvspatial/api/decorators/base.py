"""Base decorators and configuration classes for JVspatial API endpoints.

This module provides the foundational decorator infrastructure and configuration
classes used by the JVspatial API system.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class WebhookConfig:
    """Configuration for webhook endpoints.

    Attributes:
        hmac_secret: Optional HMAC secret for webhook verification
        idempotency_key_field: Header field name for idempotency keys
        idempotency_ttl_hours: Time-to-live for idempotency keys in hours
        async_processing: Whether to process webhooks asynchronously
        path_key_auth: Whether to use path-based key authentication
    """

    hmac_secret: Optional[str] = None
    idempotency_key_field: str = "X-Idempotency-Key"
    idempotency_ttl_hours: int = 24
    async_processing: bool = False
    path_key_auth: bool = False


@dataclass
class EndpointConfig:
    """Configuration for API endpoints.

    Attributes:
        path: URL path for the endpoint
        methods: HTTP methods allowed for this endpoint
        auth_required: Whether authentication is required
        permissions: List of required permissions
        roles: List of required roles
        webhook: Optional webhook configuration
        openapi_extra: Additional OpenAPI metadata
    """

    path: str
    methods: List[str] = field(default_factory=lambda: ["GET"])
    auth_required: bool = False
    permissions: List[str] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)
    webhook: Optional[WebhookConfig] = None
    openapi_extra: Dict[str, Any] = field(default_factory=dict)


class EndpointDecorator:
    """Base decorator class for API endpoints."""

    @staticmethod
    def endpoint(
        config: EndpointConfig,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Create an endpoint decorator with the given configuration.

        Args:
            config: Endpoint configuration

        Returns:
            Decorator function
        """

        def decorator(target: Callable[..., Any]) -> Callable[..., Any]:
            if inspect.isclass(target):
                # Walker endpoints (class-based) can be handled in a later pass
                # For now, attach config for server/router to process centrally
                target._endpoint_config = config
                return target
            else:
                func = target

                async def wrapper(*args: Any, **kwargs: Any):
                    return await func(*args, **kwargs)

                wrapper._endpoint_config = config  # type: ignore[attr-defined]
                return wrapper

        return decorator
