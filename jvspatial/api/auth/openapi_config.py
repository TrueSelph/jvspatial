"""OpenAPI security configuration for jvspatial API.

This module provides OpenAPI security scheme configuration for authentication
endpoints, including JWT Bearer tokens and API key authentication.
"""

from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def configure_openapi_security(app: FastAPI) -> None:
    """Configure OpenAPI security schemes for the FastAPI application.

    Args:
        app: FastAPI application instance to configure
    """
    # Get the current server from context to check auth configuration
    from jvspatial.api.context import get_current_server

    server = get_current_server()

    # Get the current OpenAPI schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Add security schemes based on server configuration
    security_schemes = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token authentication",
        }
    }

    # Only add API key authentication if it's enabled
    if server and server.config.api_key_auth_enabled:
        security_schemes["ApiKeyAuth"] = {
            "type": "apiKey",
            "in": "header",
            "name": server.config.api_key_header,
            "description": "API key authentication",
        }

    # Ensure components key exists
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}

    openapi_schema["components"]["securitySchemes"] = security_schemes

    # Add security requirements to endpoints that need authentication
    for path, path_item in openapi_schema["paths"].items():
        for method, operation in path_item.items():
            if method in ["get", "post", "put", "delete", "patch"]:
                # Check if this endpoint requires authentication
                endpoint_func = None
                for route in app.routes:
                    if (
                        hasattr(route, "path")
                        and route.path == path
                        and hasattr(route, "endpoint")
                    ):
                        endpoint_func = route.endpoint
                        break

                if endpoint_func:
                    # Check for endpoint configuration on the function
                    endpoint_config = getattr(
                        endpoint_func, "_jvspatial_endpoint_config", None
                    )

                    # Also check if this is a Walker endpoint by looking at the route's methods
                    # Walker endpoints are registered through EndpointRouter with auth parameters
                    auth_required = False
                    permissions = []
                    roles = []

                    if endpoint_config and endpoint_config.get("auth_required"):
                        auth_required = True
                        permissions = endpoint_config.get("permissions", [])
                        roles = endpoint_config.get("roles", [])
                    else:
                        # Check if this is a Walker endpoint by examining the route
                        # Walker endpoints are typically POST endpoints with specific patterns
                        if (
                            method == "post"
                            and "/api/" in path
                            and hasattr(endpoint_func, "__self__")
                            and hasattr(endpoint_func.__self__, "__class__")
                        ):
                            walker_class = endpoint_func.__self__.__class__
                            walker_config = getattr(
                                walker_class, "_jvspatial_endpoint_config", None
                            )
                            if walker_config and walker_config.get("auth_required"):
                                auth_required = True
                                permissions = walker_config.get("permissions", [])
                                roles = walker_config.get("roles", [])

                    # Additional check: if this is a Walker endpoint path pattern, check for auth attributes
                    if (
                        not auth_required
                        and method == "post"
                        and "/api/" in path
                        and hasattr(endpoint_func, "_auth_required")
                        and endpoint_func._auth_required
                    ):
                        auth_required = True
                        permissions = getattr(
                            endpoint_func, "_required_permissions", []
                        )
                        roles = getattr(endpoint_func, "_required_roles", [])

                    # Additional check: if this is an auth endpoint, check for auth attributes
                    if (
                        not auth_required
                        and "/auth/" in path
                        and hasattr(endpoint_func, "_auth_required")
                        and endpoint_func._auth_required
                    ):
                        auth_required = True
                        permissions = getattr(
                            endpoint_func, "_required_permissions", []
                        )
                        roles = getattr(endpoint_func, "_required_roles", [])

                    if auth_required:
                        # Add security requirements to this operation
                        operation["security"] = get_endpoint_security_requirements(
                            permissions=permissions, roles=roles
                        )

    # Update the app's OpenAPI schema
    app.openapi_schema = openapi_schema


def get_endpoint_security_requirements(
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
) -> List[Dict[str, List[str]]]:
    """Get security requirements for an endpoint based on permissions and roles.

    Args:
        permissions: List of required permissions
        roles: List of required roles

    Returns:
        List of security requirement dictionaries
    """
    # Get the current server from context to check auth configuration
    from jvspatial.api.context import get_current_server

    server = get_current_server()

    security_requirements: List[Dict[str, Any]] = []

    # Add JWT Bearer authentication
    security_requirements.append({"BearerAuth": []})

    # Only add API key authentication if it's enabled
    if server and server.config.api_key_auth_enabled:
        security_requirements.append({"ApiKeyAuth": []})

    return security_requirements


def add_security_to_endpoint(
    endpoint_func: Any,
    auth_required: bool = False,
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
) -> Any:
    """Add security requirements to an endpoint function.

    Args:
        endpoint_func: The endpoint function to modify
        auth_required: Whether authentication is required
        permissions: List of required permissions
        roles: List of required roles

    Returns:
        Modified endpoint function with security requirements
    """
    if not auth_required:
        return endpoint_func

    # Add security requirements to the function
    if not hasattr(endpoint_func, "__annotations__"):
        endpoint_func.__annotations__ = {}

    # Store security requirements as function attributes
    endpoint_func._security_requirements = get_endpoint_security_requirements(
        permissions=permissions, roles=roles
    )

    return endpoint_func


__all__ = [
    "configure_openapi_security",
    "get_endpoint_security_requirements",
    "add_security_to_endpoint",
]
