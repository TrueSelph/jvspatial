"""Test to verify auth decorators work properly with Swagger."""

from jvspatial.api import Server
from jvspatial.api.auth import admin_endpoint, auth_endpoint

# Create server FIRST
server = Server(
    title="Auth Test API",
    description="Testing auth/swagger integration",
    version="1.0.0",
    port=8002,
)


# Then apply decorators - they will find the server via get_current_server()
@auth_endpoint("/api/protected", methods=["GET"])
async def protected_route(endpoint):
    """Protected endpoint requiring authentication."""
    return endpoint.success(data={"message": "You are authenticated!"})


@admin_endpoint("/api/admin", methods=["GET"])
async def admin_route(endpoint):
    """Admin-only endpoint."""
    return endpoint.success(data={"message": "Admin access granted!"})


def test_configuration():
    """Test that everything is configured correctly."""
    print("=" * 70)
    print("AUTH DECORATOR INTEGRATION TEST")
    print("=" * 70)
    print()

    # Check routes were added
    print(f"1. Routes in server._custom_routes: {len(server._custom_routes)}")
    for route in server._custom_routes:
        print(f"   - {route['path']}: {route.get('openapi_extra')}")
    print()

    # Get app (this should register the routes)
    app = server.get_app()

    # Check FastAPI routes
    print(
        f"2. Routes in FastAPI app: {len([r for r in app.routes if hasattr(r, 'path')])}"
    )
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            print(f"   - {route.path}")
    print()

    # Check OpenAPI spec
    openapi = app.openapi()

    print("3. Security Schemes:")
    if "components" in openapi and "securitySchemes" in openapi["components"]:
        for name, scheme in openapi["components"]["securitySchemes"].items():
            print(f"   ✅ {name}: {scheme['type']}")
    else:
        print("   ❌ No security schemes found")
    print()

    print("4. Endpoint Security:")
    for path, path_item in openapi.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.lower() in ["get", "post", "put", "delete", "patch"]:
                security = operation.get("security", [])
                status = "✅" if security else "❌"
                print(f"   {status} {method.upper():6} {path:30} Security: {security}")
    print()

    print("=" * 70)
    if "/api/protected" in openapi.get("paths", {}):
        print("✅ SUCCESS: Auth endpoints properly configured for Swagger!")
        print("   Visit http://localhost:8002/docs to see the 'Authorize' button")
    else:
        print("❌ FAILED: Endpoints not registered")
    print("=" * 70)


if __name__ == "__main__":
    test_configuration()

    # Uncomment to run the server:
    # server.run()
