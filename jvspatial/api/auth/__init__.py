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
    from jvspatial.api import endpoint  # Public endpoints
    from jvspatial.api.auth import auth_endpoint, admin_endpoint

    @endpoint("/public/info")  # Public function endpoint
    async def public_info():
        pass

    @endpoint("/public/data")  # Public walker endpoint
    class PublicWalker(Walker):
        pass

    @auth_endpoint("/protected/info", permissions=["read_data"])  # Authenticated function
    async def protected_info():
        pass

    @auth_endpoint("/protected/data", permissions=["read_data"])  # Authenticated walker
    class ProtectedWalker(Walker):
        pass

    @admin_endpoint("/admin/users")  # Admin function endpoint
    async def manage_users():
        pass

    @admin_endpoint("/admin/process")  # Admin walker endpoint
    class AdminProcessor(Walker):
        pass
"""

from .decorators import (
    admin_endpoint,
    auth_endpoint,
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
    # Decorators - Unified decorators work with both functions and Walker classes
    "auth_endpoint",  # Unified authenticated endpoint (auto-detects functions/walkers)
    "admin_endpoint",  # Convenience decorator for admin-only endpoints
]

# Version info
__version__ = "0.0.1"
