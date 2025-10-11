"""Diagnostic script to identify why FastAPI Swagger doesn't show auth properly.

This script checks multiple potential sources of the authentication/Swagger integration problem.
"""

import json

from jvspatial.api import Server
from jvspatial.api.auth import admin_endpoint, auth_endpoint

# Create a test server
server = Server(
    title="Auth Diagnostic API",
    description="Testing auth/swagger integration",
    version="1.0.0",
    port=8001,
)


@auth_endpoint("/test/auth", methods=["GET"])
async def test_auth_endpoint(endpoint):
    """Test authenticated endpoint."""
    return endpoint.success(data={"message": "Authenticated!"})


@admin_endpoint("/test/admin", methods=["GET"])
async def test_admin_endpoint(endpoint):
    """Test admin endpoint."""
    return endpoint.success(data={"message": "Admin access!"})


def diagnose_openapi_security():
    """Diagnose OpenAPI security configuration issues."""

    print("=" * 70)
    print("FASTAPI SWAGGER AUTHENTICATION DIAGNOSTIC")
    print("=" * 70)
    print()

    # Get the FastAPI app (this triggers route registration)
    app = server.get_app()

    # Debug: print custom routes
    print("DEBUG: Custom routes registered in server._custom_routes:")
    for route in server._custom_routes:
        print(f"  - {route.get('path')}: {route.get('openapi_extra')}")
    print()

    # Debug: print actual FastAPI routes
    print("DEBUG: Actual FastAPI app.routes:")
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            print(f"  - {route.path} {route.methods}")
    print()

    # Issue 1: Check if security schemes are defined in OpenAPI spec
    print("1. Checking OpenAPI Security Schemes:")
    print("-" * 70)
    openapi_schema = app.openapi()

    if "components" in openapi_schema:
        if "securitySchemes" in openapi_schema["components"]:
            print("✅ Security schemes ARE defined:")
            print(json.dumps(openapi_schema["components"]["securitySchemes"], indent=2))
        else:
            print("❌ PROBLEM: No security schemes defined in OpenAPI spec")
            print("   This prevents Swagger from showing 'Authorize' button")
    else:
        print("❌ PROBLEM: No 'components' section in OpenAPI spec")
    print()

    # Issue 2: Check if endpoints declare security requirements
    print("2. Checking Endpoint Security Requirements:")
    print("-" * 70)
    for path, path_item in openapi_schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.lower() in ["get", "post", "put", "delete", "patch"]:
                security = operation.get("security", [])
                print(
                    f"{method.upper():6} {path:30} Security: {security if security else '❌ NONE'}"
                )
    print()

    # Issue 3: Check if routes have dependencies
    print("3. Checking Route Dependencies:")
    print("-" * 70)
    for route in app.routes:
        if hasattr(route, "endpoint") and hasattr(route, "path"):
            deps = getattr(route, "dependencies", [])
            print(f"{route.path:40} Dependencies: {len(deps)} {'✅' if deps else '❌'}")
    print()

    # Issue 4: Check auth decorator metadata
    print("4. Checking Auth Decorator Metadata:")
    print("-" * 70)
    test_func = test_auth_endpoint
    print(f"Function: {test_func.__name__}")
    print(f"  _auth_required: {getattr(test_func, '_auth_required', 'NOT SET')}")
    print(
        f"  _required_permissions: {getattr(test_func, '_required_permissions', 'NOT SET')}"
    )
    print(f"  _required_roles: {getattr(test_func, '_required_roles', 'NOT SET')}")
    print()

    # Issue 5: Check middleware configuration
    print("5. Checking Middleware Configuration:")
    print("-" * 70)
    middleware_count = len(app.user_middleware)
    print(f"Middleware count: {middleware_count}")
    for i, middleware in enumerate(app.user_middleware):
        print(f"  {i+1}. {middleware.cls.__name__}")
    print()

    # Issue 6: Check if HTTPBearer is properly configured
    print("6. Checking HTTPBearer Security Configuration:")
    print("-" * 70)
    from jvspatial.api.auth.middleware import security

    print(f"HTTPBearer instance: {security}")
    print(f"  scheme_name: {getattr(security, 'scheme_name', 'NOT SET')}")
    print(f"  auto_error: {getattr(security, 'auto_error', 'NOT SET')}")
    print()

    # Summary
    print("=" * 70)
    print("DIAGNOSIS SUMMARY")
    print("=" * 70)
    print()
    print("Most likely issues (in order of priority):")
    print()

    if "securitySchemes" not in openapi_schema.get("components", {}):
        print("🔴 CRITICAL: OpenAPI spec missing security schemes configuration")
        print("   FIX: Configure security schemes in FastAPI app creation")
        print("   LOCATION: jvspatial/jvspatial/api/server.py:_create_base_app()")
        print()

    # Check if any endpoint has security declared
    has_security = False
    for path, path_item in openapi_schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.lower() in ["get", "post", "put", "delete", "patch"]:
                if operation.get("security"):
                    has_security = True
                    break

    if not has_security:
        print("🔴 CRITICAL: Endpoints don't declare security requirements in OpenAPI")
        print(
            "   FIX: Auth decorators must inject security dependencies or use openapi_extra"
        )
        print("   LOCATION: jvspatial/jvspatial/api/auth/decorators.py:auth_endpoint()")
        print()

    print("🔍 Run this diagnostic to identify the exact issue before applying fixes")
    print()


if __name__ == "__main__":
    diagnose_openapi_security()
