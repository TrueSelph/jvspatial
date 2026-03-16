# Authentication Quickstart Guide

Get your jvspatial API secured in 5 minutes with comprehensive authentication including JWT tokens, API keys, and role-based access control.

> **💡 Standard Example**: For a complete authenticated API implementation with CRUD operations, pagination, and best practices, see:
> **📁 [`examples/api/authenticated_endpoints_example.py`](../../examples/api/authenticated_endpoints_example.py)**

## Prerequisites

- jvspatial installed: `pip install jvspatial`
- Python 3.8+ environment

## Step 1: Basic Setup (2 minutes)

### Create Your Authenticated Server

> **Note**: When `auth_enabled=True`, the server **automatically registers** authentication endpoints (`/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me`). When `auth_enabled=False`, these endpoints are **NOT registered**.

```python
# auth_server.py
import os
from jvspatial.api import Server

# Create server with authentication enabled
# This automatically registers /auth/register, /auth/login, /auth/logout, /auth/me
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
        # Optional: bootstrap admin from env on first run
        bootstrap_admin_email=os.getenv("ADMIN_EMAIL"),
        bootstrap_admin_password=os.getenv("ADMIN_PASSWORD"),
        bootstrap_admin_name=os.getenv("ADMIN_NAME"),
    ),
)

if __name__ == "__main__":
    server.run()
```

**That's it!** Your server now has full authentication with:
- User registration (`POST /api/auth/register`) — first user becomes admin (bootstrap)
- Current user (`GET /api/auth/me`) — returns authenticated user
- User login (`POST /api/auth/login`)
- JWT token validation and RBAC (roles and permissions)
- Rate limiting
- Automatic API documentation at `/docs`

> **Note**: Auth endpoints use the API prefix (default `/api`). With `JVSPATIAL_API_PREFIX=/v1`, paths become `/v1/auth/login`, etc.

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

### Streamlined Integration (Callbacks and get_auth_service)

Use callbacks to create domain entities without custom endpoints:

```python
import os
from jvspatial.api import Server, get_auth_service

async def on_user_registered(user_response, request_body):
    """Create UserNode, Organization, etc. after registration."""
    # request_body has email, password, name, organizationName, etc.
    pass

async def on_admin_bootstrapped(user_response):
    """Create UserNode when admin is bootstrapped from env."""
    pass

async def enrich_me(user_response):
    """Augment GET /auth/me response."""
    return {"display_name": user_response.name, "extra": "..."}

server = Server(
    auth=dict(
        auth_enabled=True,
        jwt_secret="...",
        bootstrap_admin_email=os.getenv("ADMIN_EMAIL"),
        bootstrap_admin_password=os.getenv("ADMIN_PASSWORD"),
    ),
    on_user_registered=on_user_registered,
    on_admin_bootstrapped=on_admin_bootstrapped,
    on_enrich_current_user=enrich_me,
)

# In custom endpoints, use the shared auth service:
auth_service = get_auth_service()
user = await auth_service.validate_token(token)
```

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
from jvspatial.core.entities import Walker, Node, on_visit

@endpoint("/spatial/query", auth=True, permissions=["read_spatial"])
class SpatialQuery(Walker):
    region: str = "north_america"

    @on_visit(Node)
    async def query(self, here: Node):
        # current_user is injected when auth=True; add as class field if needed
        # Process spatial query...
        self.response = {"data": "spatial results"}
```

### API Key Authentication

```python
# Use built-in POST /auth/api-keys when api_key_management_enabled=True
# Or create custom endpoint:
@endpoint("/create-api-key", auth=True, methods=["POST"])
async def create_key(current_user):
    from jvspatial.api.auth.api_key_service import APIKeyService
    from jvspatial.db import get_prime_database
    from jvspatial.core.context import GraphContext

    service = APIKeyService(GraphContext(database=get_prime_database()))
    plaintext_key, api_key = await service.generate_key(
        user_id=current_user.id, name="My Service Key"
    )
    return {"key_id": api_key.id, "key": plaintext_key}

# Use API key in requests
# curl -H "X-API-Key: secret-key-123" http://localhost:8000/protected/data
```

## Production Checklist

Before deploying to production:

```python
server = Server(
    db_type="json",
    db_path="./data",
    auth=dict(
        auth_enabled=True,
        jwt_secret=os.getenv("JWT_SECRET_KEY"),
        jwt_expire_minutes=1440,
    ),
)
```

Environment variables:
```bash
export JWT_SECRET_KEY="your-256-bit-secret-generated-key"
export JVSPATIAL_DB_PATH="./data"
```

## Next Steps

- **Full Documentation**: [Authentication Guide](authentication.md)
- **Complete Example**: [examples/api/authenticated_endpoints_example.py](../../examples/api/authenticated_endpoints_example.py)
- **API Reference**: [REST API Docs](rest-api.md#authentication)
- **Advanced Patterns**: [Server API Guide](server-api.md#authentication)

## Common Issues

### "No server instance available"
- Use `Server(auth={...})` and ensure your endpoint modules are imported so the server registers them
- Use `server=your_server` parameter if using multiple servers

### 401 with valid token
- **Database context**: Auth always uses the prime database. Ensure you use jvspatial 0.0.5+ which fixes 401 when `server._graph_context` differs from the prime DB.

### "Invalid token" errors
- Check that `jwt_secret` is consistent between token creation and validation
- Ensure tokens haven't expired (default 30 minutes; set `jwt_expire_minutes` as needed)
- Enable debug logging to see detailed token validation information
- Token validation decodes tokens first, then checks blacklist - expired tokens are rejected during decode

### Auth parameter injection in endpoints
- For `@endpoint(..., auth=True)`, add `user_id: str` and/or `current_user` as parameters; they are injected from `request.state.user`. No manual `if not user_id` guard needed—401 is returned automatically when missing:
  ```python
  @endpoint("/me", auth=True)
  async def get_me(user_id: str):
      return {"user_id": user_id}

  @endpoint("/tracks", methods=["GET"], auth=True)
  async def list_tracks(current_user):
      return {"tracks": [], "user": current_user.email}
  ```

### Authentication not working
- Ensure `Server(auth=dict(auth_enabled=True, ...))` is set
- Check that protected endpoints use `@endpoint(..., auth=True)` instead of just `@endpoint(...)`
- Enable debug logging to trace token validation flow and identify where validation fails
- Login succeeds even if refresh token generation fails - check access token, not just refresh token

---

**Total setup time: ~5 minutes**

Your jvspatial API is now secured with enterprise-grade authentication!