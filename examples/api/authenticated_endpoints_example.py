"""Authenticated Endpoints Example

This example demonstrates how to use @auth_endpoint and @admin_endpoint
decorators to create authenticated API endpoints with role-based and
permission-based access control.

Note: @auth_endpoint and @admin_endpoint are unified decorators that work
with both functions and Walker classes (auto-detection).

The decorators automatically handle:
- Authentication validation
- Role checking (user must have at least one required role)
- Permission checking (user must have all required permissions)
- Middleware integration
- OpenAPI/Swagger security configuration (automatic "Authorize" button)

Usage:
    python authenticated_endpoints_example.py

    Then visit http://localhost:8000/docs to see the Swagger UI with the
    "Authorize" button enabled for testing authenticated endpoints.

Note: The decorators AUTOMATICALLY configure OpenAPI security schemes,
so Swagger UI will show an "Authorize" button where you can enter:
- Bearer tokens (from /auth/login)
- API keys (format: key_id:secret)

For a complete working server with user management, see the auth setup notes below.
"""

from typing import Any, Dict

from jvspatial.api import Server
from jvspatial.api.auth import admin_endpoint, auth_endpoint
from jvspatial.api.endpoint.decorators import EndpointField
from jvspatial.core import Node, Walker, on_visit

# =============================================================================
# SERVER SETUP - Must be created BEFORE decorators
# =============================================================================

# Create server instance first so decorators can register endpoints
server = Server(
    title="Authenticated API Example",
    description="Example demonstrating auth decorators",
    version="1.0.0",
    host="0.0.0.0",
    port=8000,
)


# =============================================================================
# AUTHENTICATED FUNCTION ENDPOINTS
# =============================================================================


@auth_endpoint("/profile", methods=["GET"])
async def get_user_profile(endpoint) -> Any:
    """Get current user's profile.

    This endpoint requires authentication but no specific roles or permissions.
    Any authenticated user can access this endpoint.

    The middleware will automatically:
    - Verify the user is authenticated
    - Reject requests without valid credentials (401)
    - Reject requests from inactive users (403)
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
    - Authentication (any authenticated user)
    - Permission: "read_data"

    Users without the "read_data" permission will receive a 403 Forbidden response.
    """
    return endpoint.success(data={"message": "Protected data accessed successfully"})


@auth_endpoint("/data/write", methods=["POST"], permissions=["read_data", "write_data"])
async def write_protected_data(data: Dict[str, Any], endpoint) -> Any:
    """Write protected data.

    This endpoint requires:
    - Authentication
    - Permissions: "read_data" AND "write_data" (both required)

    The user must have ALL specified permissions.
    """
    return endpoint.success(
        data={"message": "Data written successfully", "written": data}
    )


@auth_endpoint(
    "/reports/generate", methods=["POST"], roles=["analyst", "manager", "admin"]
)
async def generate_report(endpoint) -> Any:
    """Generate a report.

    This endpoint requires:
    - Authentication
    - Role: "analyst" OR "manager" OR "admin" (at least one required)

    The user must have AT LEAST ONE of the specified roles.
    """
    return endpoint.success(data={"message": "Report generation started"})


@auth_endpoint(
    "/data/admin",
    methods=["GET", "POST", "DELETE"],
    roles=["admin"],
    permissions=["admin_access", "manage_data"],
)
async def admin_data_management(endpoint) -> Any:
    """Administrative data management.

    This endpoint requires:
    - Authentication
    - Role: "admin"
    - Permissions: "admin_access" AND "manage_data"

    Both role and permission checks must pass.
    """
    return endpoint.success(data={"message": "Admin operation completed"})


# Convenience decorator for admin-only endpoints
@admin_endpoint("/admin/settings", methods=["GET", "PUT"])
async def manage_settings(endpoint) -> Any:
    """Manage system settings (admin only).

    @admin_endpoint is equivalent to:
    @auth_endpoint(path, roles=["admin"])

    This is a convenience decorator for admin-only endpoints.
    """
    return endpoint.success(data={"message": "Settings retrieved"})


# =============================================================================
# AUTHENTICATED WALKER ENDPOINTS
# =============================================================================


@auth_endpoint("/users/analyze", methods=["POST"], permissions=["read_users"])
class AnalyzeUsersWalker(Walker):
    """Analyze user data with graph traversal.

    This walker endpoint requires:
    - Authentication
    - Permission: "read_users"

    Walker endpoints work the same as function endpoints but use
    Walker classes for graph traversal operations.
    """

    department: str = EndpointField(
        default="all",
        description="Department to analyze",
        examples=["engineering", "marketing", "sales"],
    )

    max_depth: int = EndpointField(
        default=3, description="Maximum traversal depth", ge=1, le=10
    )

    @on_visit("User")
    async def analyze_user(self, here: Node):
        """Analyze user nodes during traversal.

        Args:
            here: The visited User node
        """
        # Filter by department if specified
        if self.department != "all" and here.department != self.department:
            self.skip()
            return

        # Collect user data for analysis
        self.report(
            {
                "user_analyzed": {
                    "id": here.id,
                    "name": here.name,
                    "department": here.department,
                }
            }
        )

        # Continue traversal to connected users
        if self.max_depth > 0:
            self.max_depth -= 1
            connected = await here.nodes(node=["User"])
            await self.visit(connected)


@auth_endpoint(
    "/graph/process",
    methods=["POST"],
    roles=["data_scientist", "analyst", "admin"],
    permissions=["process_graph_data"],
)
class ProcessGraphWalker(Walker):
    """Process graph data with role and permission requirements.

    This walker endpoint requires:
    - Authentication
    - Role: "data_scientist" OR "analyst" OR "admin"
    - Permission: "process_graph_data"
    """

    operation: str = EndpointField(
        description="Operation to perform", examples=["count", "aggregate", "export"]
    )

    filters: Dict[str, Any] = EndpointField(
        default_factory=dict, description="Filters to apply during traversal"
    )

    @on_visit(Node)
    async def process_node(self, here: Node):
        """Process any node type based on operation.

        Args:
            here: The visited Node
        """
        # Apply operation based on request
        if self.operation == "count":
            self.report({"node_counted": here.id})
        elif self.operation == "aggregate":
            self.report({"node_data": {"id": here.id, "type": here.__class__.__name__}})

        # Continue traversal with filters
        next_nodes = await here.nodes(**self.filters)
        await self.visit(next_nodes)


# =============================================================================
# AUTHENTICATION SETUP NOTES
# =============================================================================
"""
For a fully functional authenticated server, you need to:

1. Add authentication middleware:
   from jvspatial.api.auth import AuthenticationMiddleware
   server.app.add_middleware(AuthenticationMiddleware)

2. Configure auth settings:
   from jvspatial.api.auth import configure_auth
   configure_auth(
       jwt_secret_key="your-secret-key",  # pragma: allowlist secret
       jwt_expiration_hours=24
   )

3. Create users with roles/permissions:
   from jvspatial.api.auth import User
   user = await User.create(
       username="analyst",
       email="analyst@example.com",
       password="secure_password",  # pragma: allowlist secret
       roles=["analyst"],
       permissions=["read_data", "read_users"]
   )
"""


# =============================================================================
# DECORATOR VALIDATION SUMMARY
# =============================================================================
"""
Authentication Decorator Summary:

1. @auth_endpoint - Unified authenticated endpoint (auto-detects functions/walkers)
   - Requires authentication by default
   - Optional: permissions (list of required permissions - ALL must be present)
   - Optional: roles (list of required roles - user must have AT LEAST ONE)
   - Optional: methods (HTTP methods, default: ["GET"] for functions, ["POST"] for walkers)
   - Works with both function endpoints and Walker classes (automatically detected)

2. @admin_endpoint - Unified admin-only endpoint (auto-detects functions/walkers)
   - Convenience decorator equivalent to @auth_endpoint(roles=["admin"])
   - Works with both function endpoints and Walker classes (automatically detected)
   - Optional: methods (HTTP methods, default: ["GET"] for functions, ["POST"] for walkers)

Authentication Flow:
1. Request arrives at authenticated endpoint
2. Middleware checks for valid credentials (JWT token or API key)
3. If no credentials or invalid: 401 Unauthorized
4. If user is inactive: 403 Forbidden
5. If permissions required: Check user has ALL required permissions
   - Missing permission: 403 Forbidden with permission details
6. If roles required: Check user has AT LEAST ONE required role
   - Missing role: 403 Forbidden with role details
7. If all checks pass: Execute endpoint logic

Middleware Integration:
- Decorators store metadata on the endpoint function/class
- AuthenticationMiddleware reads this metadata
- Middleware performs all authentication/authorization checks
- Current user is available in request.state.current_user
- Use get_current_user(request) to access authenticated user

Best Practices:
✅ Use @auth_endpoint for authenticated endpoints (functions or walkers)
✅ Specify permissions for granular access control
✅ Specify roles for role-based access control
✅ Combine permissions and roles when both are needed
✅ Use @admin_endpoint for admin-only features (functions or walkers)
✅ Follow 'here' naming convention in walker @on_visit methods

❌ Don't use regular @endpoint for endpoints that need authentication
❌ Don't manually check authentication in endpoint logic (middleware handles it)
❌ Don't use @route or @server.route (use standard decorators)
"""


if __name__ == "__main__":
    print("=" * 70)
    print("Authenticated Endpoints Example")
    print("=" * 70)
    print()
    print("This example demonstrates @auth_endpoint and @admin_endpoint")
    print("unified decorators for creating authenticated API endpoints.")
    print("These decorators work with both functions and Walker classes.")
    print()
    print("Endpoints registered:")
    print("  - GET  /api/profile               (authenticated)")
    print("  - GET  /api/data/read             (permission: read_data)")
    print("  - POST /api/data/write            (permissions: read_data, write_data)")
    print("  - POST /api/reports/generate      (roles: analyst, manager, admin)")
    print("  - *    /api/data/admin            (role: admin + permissions)")
    print("  - *    /api/admin/settings        (admin only)")
    print("  - POST /api/users/analyze         (permission: read_users)")
    print("  - POST /api/graph/process         (role + permission)")
    print()
    print("Note: This is a demonstration of decorator usage only.")
    print("For a working server, see the authentication middleware setup")
    print("documentation in the create_authenticated_server() docstring.")
    print()
    print("=" * 70)

    # Uncomment to run the server:
    server.run()
