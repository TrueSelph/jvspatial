"""Authentication system for jvspatial framework.

This module provides a complete authentication and authorization system
that integrates seamlessly with the jvspatial database and server architecture.

Features:
- User management with spatial-aware permissions
- JWT token authentication for sessions
- API key authentication for services
- Role-based access control (RBAC)
- Rate limiting and security middleware
- Spatial region and node type permissions
- Complete authentication endpoints

Usage:
    # Basic setup
    from jvspatial.api.auth import configure_auth, AuthenticationMiddleware
    from jvspatial.api import create_server

    # Configure authentication
    configure_auth(
        jwt_secret_key="your-secret-key",  # pragma: allowlist secret
        jwt_expiration_hours=24,
        rate_limit_enabled=True
    )

    # Create server with authentication
    server = create_server(title="My Authenticated API")

    # Add authentication middleware
    server.app.add_middleware(AuthenticationMiddleware)

    # Use decorators for different access levels
    from jvspatial.api import endpoint, walker_endpoint  # Public endpoints
    from jvspatial.api.auth import auth_endpoint, auth_walker_endpoint, admin_endpoint

    @endpoint("/public/info")  # Public function endpoint
    async def public_info():
        pass

    @walker_endpoint("/public/data")  # Public walker endpoint
    class PublicWalker(Walker):
        pass

    @auth_endpoint("/protected/info", permissions=["read_data"])  # Authenticated
    async def protected_info():
        pass

    @auth_walker_endpoint("/protected/data", permissions=["read_data"])
    class ProtectedWalker(Walker):
        pass

    @admin_endpoint("/admin/users")
    async def manage_users():
        pass
"""

from .decorators import authenticated_endpoint  # Aliases
from .decorators import (
    AuthAwareEndpointProcessor,
    admin_endpoint,
    admin_walker_endpoint,
    auth_endpoint,
    auth_walker_endpoint,
    authenticated_walker_endpoint,
    require_admin,
    require_authenticated_user,
    require_permissions,
    require_roles,
)
from .entities import (
    APIKey,
    APIKeyInvalidError,
    AuthenticationError,
    AuthorizationError,
    InvalidCredentialsError,
    RateLimitError,
    Session,
    SessionExpiredError,
    User,
    UserNotFoundError,
)
from .middleware import (
    AuthConfig,
    AuthenticationMiddleware,
    JWTManager,
    RateLimiter,
    authenticate_user,
    configure_auth,
    create_user_session,
    get_admin_user,
    get_current_active_user,
    get_current_user,
    get_current_user_dependency,
    refresh_session,
    security,
)

# Note: Endpoints are defined in endpoints.py but not auto-registered
# They need to be manually registered when setting up a server

__all__ = [
    # Entities
    "User",
    "APIKey",
    "Session",
    # Exceptions
    "AuthenticationError",
    "AuthorizationError",
    "RateLimitError",
    "InvalidCredentialsError",
    "UserNotFoundError",
    "SessionExpiredError",
    "APIKeyInvalidError",
    # Configuration and middleware
    "AuthConfig",
    "configure_auth",
    "AuthenticationMiddleware",
    "RateLimiter",
    "JWTManager",
    # Authentication utilities
    "get_current_user",
    "create_user_session",
    "authenticate_user",
    "refresh_session",
    "security",
    "get_current_user_dependency",
    "get_current_active_user",
    "get_admin_user",
    # Decorators
    "auth_walker_endpoint",
    "auth_endpoint",
    "authenticated_walker_endpoint",
    "authenticated_endpoint",  # Aliases
    "admin_walker_endpoint",
    "admin_endpoint",
    "AuthAwareEndpointProcessor",
    # Utility functions
    "require_authenticated_user",
    "require_permissions",
    "require_roles",
    "require_admin",
]

# Version info
__version__ = "0.0.1"
