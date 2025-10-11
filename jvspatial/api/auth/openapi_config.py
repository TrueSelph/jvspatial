"""OpenAPI security configuration for authenticated endpoints.

This module provides automatic configuration of OpenAPI security schemes
when authentication decorators are used, ensuring Swagger UI displays
the 'Authorize' button for testing authenticated endpoints.
"""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

if TYPE_CHECKING:
    from fastapi import FastAPI


# Track if security schemes have been configured
_security_schemes_configured = False


def get_security_schemes() -> Dict[str, Dict[str, Any]]:
    """Get the OpenAPI security schemes for authentication.

    Returns:
        Dictionary of security scheme definitions for OpenAPI spec
    """
    return {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "JWT token authentication. Obtain token from /auth/login endpoint. "
                "Format: Bearer <token>"
            ),
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": (
                "API Key authentication. Format: key_id:secret_key. "
                "Create keys at /auth/api-keys endpoint."
            ),
        },
    }


def configure_openapi_security(app: "FastAPI") -> None:
    """Configure OpenAPI security schemes in FastAPI app.

    This function modifies the FastAPI app's OpenAPI schema generation
    to include security scheme definitions, enabling Swagger UI to show
    the 'Authorize' button.

    Args:
        app: FastAPI application instance
    """
    global _security_schemes_configured

    if _security_schemes_configured:
        return  # Already configured

    # Store original openapi function
    original_openapi = app.openapi

    def custom_openapi() -> Dict[str, Any]:
        """Custom OpenAPI schema generator with security schemes."""
        # Call original to get base schema
        if hasattr(original_openapi, "__self__"):
            # It's a bound method, call it normally
            schema = original_openapi()
        else:
            # It's a function, call it
            schema = original_openapi()

        # Add security schemes if not already present
        if "components" not in schema:
            schema["components"] = {}

        if "securitySchemes" not in schema["components"]:
            schema["components"]["securitySchemes"] = get_security_schemes()
        else:
            # Merge with existing schemes
            schema["components"]["securitySchemes"].update(get_security_schemes())

        return cast(Dict[str, Any], schema)

    # Replace openapi function
    app.openapi = custom_openapi
    _security_schemes_configured = True


def get_endpoint_security_requirements(
    permissions: Optional[list] = None, roles: Optional[list] = None
) -> list:
    """Get security requirements for an endpoint based on permissions/roles.

    Args:
        permissions: List of required permissions
        roles: List of required roles

    Returns:
        List of security requirement dictionaries for OpenAPI spec
    """
    # For authenticated endpoints, allow both Bearer and API Key auth
    return [
        {"BearerAuth": []},
        {"ApiKeyAuth": []},
    ]


def ensure_server_has_security_config(server=None) -> None:
    """Ensure server's FastAPI app has security schemes configured.

    This is called automatically by auth decorators to configure
    OpenAPI security schemes on first use.

    Args:
        server: Server instance (uses current server if None)
    """
    if server is None:
        from jvspatial.api.context import get_current_server

        server = get_current_server()

    if server is None:
        # No server available yet - will be configured later
        return

    # Only configure if app already exists - don't create it prematurely
    # The security config will be applied when get_app() is called
    app = getattr(server, "app", None)

    if app is not None:
        configure_openapi_security(app)


__all__ = [
    "get_security_schemes",
    "configure_openapi_security",
    "get_endpoint_security_requirements",
    "ensure_server_has_security_config",
]
