# Authentication Quickstart Guide

Get your jvspatial API secured in 5 minutes with comprehensive authentication including JWT tokens, API keys, and role-based access control.

> **💡 Standard Example**: For a complete authenticated API implementation with CRUD operations, pagination, and best practices, see:
> **📁 [`examples/api/authenticated_endpoints_example.py`](../../examples/api/authenticated_endpoints_example.py)**

## Prerequisites

- jvspatial installed: `pip install jvspatial`
- Python 3.8+ environment

## Step 1: Basic Setup (2 minutes)

### Create Your Authenticated Server

> **Note**: When `auth_enabled=True`, the server **automatically registers** authentication endpoints (`/auth/register`, `/auth/login`, `/auth/logout`). When `auth_enabled=False`, these endpoints are **NOT registered**.

```python
# auth_server.py
from jvspatial.api import Server

# Create server with authentication enabled
# This automatically registers /auth/register, /auth/login, /auth/logout
server = Server(
    title="My Secure API",
    description="Authenticated spatial data API",
    version="1.0.0",
    db_type="json",
    db_path="myapp_db",
    auth=dict(
        auth_enabled=True,
        jwt_secret="your-super-secret-key-change-in-production",
        jwt_expire_minutes=1440,  # 24 hours
    ),
)

if __name__ == "__main__":
    server.run()
```

**That's it!** Your server now has full authentication with:
- User registration (`POST /api/auth/register`) — first user becomes admin (bootstrap)
- User login (`POST /api/auth/login`)
- JWT token validation and RBAC (roles and permissions)
- Rate limiting
- Automatic API documentation at `/docs`

## Step 2: Create Protected Endpoints (1 minute)

```python
from jvspatial.api import endpoint

# Public endpoint - no authentication
@endpoint("/public/info")
async def public_info():
    return {"message": "Anyone can access this"}

# Protected endpoint - requires login
@endpoint("/protected/data", auth=True)
async def protected_data():
    return {"message": "Must be logged in to see this"}

# Admin-only endpoint - requires admin role (require_any: user needs one of the listed roles)
@endpoint("/admin/users", auth=True, roles=["admin"])
async def admin_users():
    return {"message": "Only admins can access this"}

# Permission-based endpoint - requires specific permission (require_all)
@endpoint("/reports", auth=True, permissions=["reports:read"])
async def get_reports():
    return {"reports": ["Monthly", "Weekly"]}

# Both roles and permissions - both must pass
@endpoint("/advanced", auth=True, roles=["admin"], permissions=["advanced:write"])
async def advanced_ops():
    return {"message": "Admin with advanced:write permission"}
```

## Step 3: Create Your First User (1 minute)

### First-user bootstrap (automatic)

When no users exist, `POST /api/auth/register` creates the first user and assigns the `admin` role. This is the recommended way to bootstrap your application.

### Option A: Via API (Recommended)

```bash
# Start your server
python auth_server.py

# Register first user (becomes admin automatically)
curl -X POST "http://localhost:8000/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "admin123"}'

# Login to get token
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "admin123"}'
```

### Option B: Admin creates users (after bootstrap)

Once users exist, public registration is disabled. Admins create users via:

```bash
# Admin creates a new user with roles
curl -X POST "http://localhost:8000/api/auth/admin/users" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "user123",
    "roles": ["user"],
    "permissions": []
  }'
```

## Step 4: Test Authentication (1 minute)

```bash
# Get access token from login response
TOKEN="your-jwt-token-here"

# Access protected endpoint
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/protected/data"

# Access admin endpoint (requires admin role)
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/admin/users"
```

## Complete Working Example

```python
from jvspatial.api import Server, endpoint

server = Server(
    title="Quick Auth Demo",
    db_type="json",
    db_path="quick_auth_db",
    auth=dict(auth_enabled=True, jwt_secret="demo-secret-key"),
)

@endpoint("/public")
async def public():
    return {"message": "Public data"}

@endpoint("/protected", auth=True)
async def protected():
    return {"message": "Protected data"}

@endpoint("/admin", auth=True, roles=["admin"])
async def admin():
    return {"message": "Admin only"}

if __name__ == "__main__":
    server.run()
```

Run it: `python quickstart.py`. Register the first user via `POST /api/auth/register` — they become admin automatically. Visit: http://localhost:8000/docs

## Advanced Features (Optional)

### Role-Based Access Control (RBAC)

- **Roles**: `require_any` — user needs one of the listed roles
- **Permissions**: `require_all` — user must have all listed permissions
- **Both**: When both `roles` and `permissions` are specified, both checks must pass
- **Admin**: The `admin` role has `*` (all permissions) by default

```python
from jvspatial.api import endpoint

# Require specific permission (user must have reports:read)
@endpoint("/reports", auth=True, permissions=["reports:read"])
async def get_reports():
    return {"reports": ["Monthly", "Weekly"]}

# Require one of the listed roles (analyst or admin)
@endpoint("/analyze", auth=True, roles=["analyst", "admin"])
async def analyze_data():
    return {"analysis": "Complex analysis results"}

# Both roles and permissions required
@endpoint("/advanced", auth=True, roles=["admin"], permissions=["advanced:write"])
async def advanced_ops():
    return {"message": "Admin with advanced:write permission"}
```

### Admin user management endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/auth/admin/users` | POST | Create user with roles and permissions |
| `/api/auth/admin/users` | GET | List users (admin-only) |
| `/api/auth/admin/users/{user_id}/roles` | PATCH | Update user roles |
| `/api/auth/admin/users/{user_id}/permissions` | PATCH | Update user direct permissions |

### Spatial Permissions

```python
from jvspatial.api import endpoint
from jvspatial.api.auth import get_current_user
from jvspatial.core.entities import Walker, Node, on_visit

@endpoint("/spatial/query", auth=True, permissions=["read_spatial"])
class SpatialQuery(Walker):
    region: str = "north_america"

    @on_visit(Node)
    async def query(self, here: Node):
        current_user = get_current_user(self.request)

        # Check if user can access this region
        if not current_user.can_access_region(self.region):
            self.response = {"error": "Access denied to region"}
            return

        # Process spatial query...
        self.response = {"data": "spatial results"}
```

### API Key Authentication

```python
# Create API key for a user
@endpoint("/create-api-key", auth=True, methods=["POST"])
async def create_key(request: Request):
    from jvspatial.api.auth import APIKey, get_current_user

    user = get_current_user(request)
    api_key = await APIKey.create(
        name="My Service Key",
        key_id="service-key-1",
        key_hash=APIKey.hash_key("secret-key-123"),
        user_id=user.id
    )
    return {"key_id": api_key.key_id, "secret": "secret-key-123"}

# Use API key in requests
# curl -H "X-API-Key: secret-key-123" http://localhost:8000/protected/data
```

## Production Checklist

Before deploying to production:

```python
configure_auth(
    jwt_secret_key=os.getenv("JWT_SECRET_KEY"),  # From environment variable
    jwt_expiration_hours=24,
    rate_limit_enabled=True,
    require_https=True,  # Enable HTTPS requirement
    session_cookie_secure=True,  # Secure cookies
)
```

Environment variables:
```bash
export JWT_SECRET_KEY="your-256-bit-secret-generated-key"
export JVSPATIAL_REQUIRE_HTTPS=true
export JVSPATIAL_RATE_LIMIT_ENABLED=true
```

## Next Steps

- **Full Documentation**: [Authentication Guide](authentication.md)
- **Complete Example**: [examples/auth_demo.py](../examples/auth_demo.py)
- **API Reference**: [REST API Docs](rest-api.md#authentication)
- **Advanced Patterns**: [Server API Guide](server-api.md#authentication)

## Common Issues

### "No server instance available"
- Make sure you call `configure_auth()` before creating decorators
- Use `server=your_server` parameter if using multiple servers

### "Invalid token" errors
- Check that `jwt_secret_key` is consistent between token creation and validation
- Ensure tokens haven't expired (default 24 hours)
- Enable debug logging to see detailed token validation information
- Token validation decodes tokens first, then checks blacklist - expired tokens are rejected during decode

### Rate limiting too strict
- Adjust `default_rate_limit_per_hour` in `configure_auth()`
- Set `rate_limit_enabled=False` for development

### Authentication not working
- Ensure `AuthenticationMiddleware` is added to your server
- Check that protected endpoints use `@endpoint(..., auth=True)` instead of just `@endpoint(...)`
- Enable debug logging to trace token validation flow and identify where validation fails
- Login succeeds even if refresh token generation fails - check access token, not just refresh token

---

**Total setup time: ~5 minutes**

Your jvspatial API is now secured with enterprise-grade authentication!