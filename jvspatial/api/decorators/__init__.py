"""API decorators for routes and fields.

This module provides decorators for both route-level and field-level configuration:

Route Decorators (function/class level):
    - @endpoint: Basic endpoint decorator
    - @auth_endpoint: Authenticated endpoint decorator
    - @webhook_endpoint: Webhook endpoint decorator
    - @admin_endpoint: Admin-only endpoint decorator

Field Decorators (Pydantic field level):
    - endpoint_field(): Configure field behavior in API endpoints

Examples:
    Route decorators (applied to functions/classes):
        @endpoint("/api/users", methods=["GET"])
        async def get_users():
            return {"users": [...]}

        @auth_endpoint("/api/admin", roles=["admin"])
        async def admin_panel():
            return {"admin": "dashboard"}

    Field decorators (applied to Pydantic model fields):
        class User(BaseModel):
            name: str = endpoint_field(
                description="User name",
                endpoint_required=True
            )
            password: str = endpoint_field(
                exclude_endpoint=True  # Hide from API
            )
"""

# Field decorators
from .field import (
    EndpointField,
    EndpointFieldInfo,
    endpoint_field,
)

# Route decorators
from .route import (
    admin_endpoint,
    auth_endpoint,
    endpoint,
    webhook_endpoint,
)

# Route configuration (for advanced users)
from .route_config import (
    EndpointConfig,
    EndpointDecorator,
    WebhookConfig,
)

__all__ = [
    # Route decorators (function/class level)
    "endpoint",
    "auth_endpoint",
    "webhook_endpoint",
    "admin_endpoint",
    # Field decorators (field level)
    "endpoint_field",
    "EndpointField",
    "EndpointFieldInfo",
    # Configuration classes (advanced)
    "EndpointConfig",
    "WebhookConfig",
    "EndpointDecorator",
]
