"""Authenticated Endpoints Example with Centralized Authentication

This example demonstrates how to use @auth_endpoint and @admin_endpoint
decorators with centralized authentication endpoints that are automatically
provided by the jvspatial framework.

The centralized authentication system automatically provides:
- POST /api/auth/register - User registration
- POST /api/auth/login - User login
- POST /api/auth/logout - User logout
- GET  /api/auth/profile - Get current user profile
- POST /api/auth/refresh - Refresh JWT token

These endpoints are automatically registered when the server starts,
eliminating the need to manually implement authentication endpoints.

Usage:
    python authenticated_endpoints_example.py

    Then visit http://localhost:8000/docs to see the Swagger UI with the
    "Authorize" button enabled for testing authenticated endpoints.

How to test:
    1. Register a new user: POST /api/auth/register (with email, password)
    2. Login to get token: POST /api/auth/login (with email and password)
    3. Use the token in the "Authorize" button in Swagger UI
    4. Test the authenticated endpoints below

Example curl commands:
    # Register a new user
    curl -X POST http://localhost:8000/api/auth/register \
         -H "Content-Type: application/json" \
         -d '{"email": "test@example.com", "password": "testpass123", "confirm_password": "testpass123"}'  # pragma: allowlist secret

    # Login with email
    curl -X POST http://localhost:8000/api/auth/login \
         -H "Content-Type: application/json" \
         -d '{"email": "test@example.com", "password": "testpass123"}'  # pragma: allowlist secret

    # Use token to access protected endpoint
    curl -X GET http://localhost:8000/api/profile \
         -H "Authorization: Bearer <token_from_login>"
"""

from __future__ import annotations

from typing import Any, Dict

from jvspatial.api import Server, admin_endpoint, auth_endpoint
from jvspatial.api.auth.middleware import configure_auth
from jvspatial.api.decorators import EndpointField
from jvspatial.core import Walker

# =============================================================================
# SERVER SETUP - Must be created BEFORE decorators
# =============================================================================

# Configure authentication BEFORE creating server
configure_auth(
    jwt_secret_key="jvspatial-demo-secret-key-2024",  # pragma: allowlist secret
    jwt_expiration_hours=24,
    rate_limit_enabled=True,
)

# Create server instance first so decorators can register endpoints
server = Server(
    title="Authenticated API Example with Centralized Auth",
    description="Example demonstrating auth decorators with centralized authentication",
    version="1.0.0",
    host="0.0.0.0",
    port=8000,
)

# =============================================================================
# CENTRALIZED AUTHENTICATION ENDPOINTS
# =============================================================================

# Import the auth endpoints to ensure they are registered
# This is the key to making the centralized auth system work
from jvspatial.api.auth.endpoints import (
    get_user_profile,
    login_user,
    logout_user,
    refresh_token,
    register_user,
)

# The jvspatial framework automatically provides standard authentication endpoints:
# - POST /api/auth/register - User registration
# - POST /api/auth/login - User login
# - POST /api/auth/logout - User logout
# - GET  /api/auth/profile - Get current user profile
# - POST /api/auth/refresh - Refresh JWT token
#
# These endpoints are automatically available when using @auth_endpoint decorators.

print("ℹ️  Demo users can be created via the /api/auth/register endpoint")
print("   Example: POST /api/auth/register with email/password")

# =============================================================================
# AUTHENTICATED FUNCTION ENDPOINTS
# =============================================================================


@auth_endpoint("/profile", methods=["GET"])
async def get_user_profile_endpoint(endpoint) -> Any:
    """Get current user's profile.

    This endpoint requires authentication but no specific roles or permissions.
    Any authenticated user can access this endpoint.
    """
    return endpoint.success(
        data={
            "message": "Profile retrieved",
            "note": "User info available from middleware",
        }
    )


@auth_endpoint("/data/read", methods=["GET"], permissions=["read_data"])
async def read_protected_data(endpoint) -> Any:
    """Read protected data.

    This endpoint requires:
    - Authentication
    - Permission: "read_data"
    """
    return endpoint.success(data={"message": "Protected data accessed successfully"})


@auth_endpoint("/data/write", methods=["POST"], permissions=["write_data"])
async def write_protected_data(data: Dict[str, Any], endpoint) -> Any:
    """Write protected data.

    This endpoint requires:
    - Authentication
    - Permission: "write_data"
    """
    return endpoint.success(
        data={"message": "Data written successfully", "written": data}
    )


@auth_endpoint("/reports/generate", methods=["POST"], roles=["analyst", "admin"])
async def generate_report(endpoint) -> Any:
    """Generate a report.

    This endpoint requires:
    - Authentication
    - Role: "analyst" OR "admin"
    """
    return endpoint.success(data={"message": "Report generation started"})


@admin_endpoint("/admin/settings", methods=["GET"])
async def get_settings(endpoint) -> Any:
    """Get system settings (admin only).

    @admin_endpoint is equivalent to:
    @auth_endpoint(path, roles=["admin"])
    """
    return endpoint.success(data={"message": "Settings retrieved"})


@admin_endpoint("/admin/settings", methods=["PUT"])
async def update_settings(settings_data: Dict[str, Any], endpoint) -> Any:
    """Update system settings (admin only).

    @admin_endpoint is equivalent to:
    @auth_endpoint(path, roles=["admin"])
    """
    return endpoint.success(
        data={"message": "Settings updated", "updated": settings_data}
    )


# =============================================================================
# AUTHENTICATED WALKER ENDPOINTS
# =============================================================================


@auth_endpoint("/users/analyze", methods=["POST"], permissions=["read_users"])
class AnalyzeUsersWalker(Walker):
    """Analyze user data with graph traversal.

    This walker endpoint requires:
    - Authentication
    - Permission: "read_users"
    """

    department: str = EndpointField(
        default="all",
        description="Department to analyze",
        examples=["engineering", "marketing", "sales"],
    )

    async def analyze_users(self, endpoint) -> Any:
        """Analyze users in the specified department."""
        analysis_result = {
            "department": self.department,
            "users_analyzed": 42,
            "insights": ["High engagement", "Growth potential"],
        }

        return endpoint.success(
            data={
                "message": "User analysis completed",
                "analysis": analysis_result,
            }
        )


# =============================================================================
# SERVER STARTUP
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Authenticated Endpoints Example with Centralized Authentication")
    print("=" * 70)
    print("This example demonstrates @auth_endpoint and @admin_endpoint")
    print("decorators with centralized authentication endpoints.")
    print("These decorators work with both functions and Walker classes.")
    print("Endpoints registered:")
    print("  - GET  /profile                   (authenticated)")
    print("  - GET  /data/read                 (permission: read_data)")
    print("  - POST /data/write                (permission: write_data)")
    print("  - POST /reports/generate          (roles: analyst, admin)")
    print("  - GET  /admin/settings            (admin only)")
    print("  - PUT  /admin/settings            (admin only)")
    print("  - POST /users/analyze             (permission: read_users)")
    print()
    print("Centralized Auth Endpoints (automatically provided):")
    print("  - POST /api/auth/register         (user registration)")
    print("  - POST /api/auth/login            (user login)")
    print("  - POST /api/auth/logout           (user logout)")
    print("  - GET  /api/auth/profile          (get user profile)")
    print("  - POST /api/auth/refresh          (refresh JWT token)")
    print("=" * 70)
    print("ℹ️  Demo users can be created via the /api/auth/register endpoint")
    print("   Example: POST /api/auth/register with email/password")
    print("=" * 70)

    # Uncomment to run the server:
    server.run()
