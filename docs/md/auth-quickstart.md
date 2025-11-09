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
    auth_enabled=True,  # Enables authentication and registers auth endpoints
    jwt_auth_enabled=True,
    jwt_secret="your-super-secret-key-change-in-production",
    jwt_expire_minutes=1440  # 24 hours
)

if __name__ == "__main__":
    server.run()
```

**That's it!** Your server now has full authentication with:
- User registration (`POST /auth/register`)
- User login (`POST /auth/login`)
- JWT token validation
- Rate limiting
- Automatic API documentation at `/docs`

## Step 2: Create Protected Endpoints (1 minute)

```python
from jvspatial.api import endpoint  # Public endpoints
from jvspatial.api.auth import auth_endpoint, admin_endpoint  # Protected endpoints

# Public endpoint - no authentication
@endpoint("/public/info")
async def public_info():
    return {"message": "Anyone can access this"}

# Protected endpoint - requires login
@auth_endpoint("/protected/data")
async def protected_data():
    return {"message": "Must be logged in to see this"}

# Admin-only endpoint - requires admin role
@admin_endpoint("/admin/users")
async def admin_users():
    return {"message": "Only admins can access this"}
```

## Step 3: Create Your First User (1 minute)

### Option A: Via API (Recommended)

Start your server and use the built-in registration:

```bash
# Start your server
python auth_server.py

# Register a user
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "admin123",
    "confirm_password": "admin123"
  }'

# Login to get token
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'
```

### Option B: Programmatically

```python
# Add this to your server startup
@server.on_startup
async def create_admin():
    from jvspatial.api.auth import User

    # Check if admin exists
    admin = await User.find_by_username("admin")
    if not admin:
        # Create admin user
        admin = await User.create(
            username="admin",
            email="admin@example.com",
            password_hash=User.hash_password("admin123"),
            is_admin=True  # Make them admin
        )
        print(f"Created admin user: {admin.username}")
```

## Step 4: Test Authentication (1 minute)

```bash
# Get access token from login response
TOKEN="your-jwt-token-here"

# Access protected endpoint
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/protected/data"

# Access admin endpoint (if you're admin)
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/admin/users"
```

## Complete Working Example

Here's a complete 20-line authenticated server:

```python
from jvspatial.api import create_server, endpoint
from jvspatial.api.auth import configure_auth, AuthenticationMiddleware, auth_endpoint, admin_endpoint, User

# Configure authentication
configure_auth(jwt_secret_key="demo-secret-key")

# Create server with middleware
server = create_server(title="Quick Auth Demo")
server.app.add_middleware(AuthenticationMiddleware)

@endpoint("/public")
async def public(): return {"message": "Public data"}

@auth_endpoint("/protected")
async def protected(): return {"message": "Protected data"}

@admin_endpoint("/admin")
async def admin(): return {"message": "Admin only"}

@server.on_startup
async def setup():
    if not await User.find_by_username("admin"):
        await User.create(username="admin", email="admin@test.com",
                         password_hash=User.hash_password("admin123"), is_admin=True)

server.run() if __name__ == "__main__" else None
```

Run it: `python quickstart.py`

Visit: http://localhost:8000/docs

## Advanced Features (Optional)

### Role-Based Access Control

```python
from jvspatial.api.auth import auth_endpoint

# Require specific permissions
@auth_endpoint("/reports", permissions=["read_reports"])
async def get_reports():
    return {"reports": ["Monthly", "Weekly"]}

# Require specific roles
@auth_endpoint("/analyze", roles=["analyst", "admin"])
async def analyze_data():
    return {"analysis": "Complex analysis results"}

# Multiple requirements
@auth_endpoint("/advanced", permissions=["advanced_ops"], roles=["admin"])
async def advanced_ops():
    return {"message": "Advanced operations"}
```

### Spatial Permissions

```python
from jvspatial.api.auth import auth_endpoint, get_current_user
from jvspatial.core.entities import Walker, Node, on_visit

@auth_endpoint("/spatial/query", permissions=["read_spatial"])
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
@auth_endpoint("/create-api-key", methods=["POST"])
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

### Rate limiting too strict
- Adjust `default_rate_limit_per_hour` in `configure_auth()`
- Set `rate_limit_enabled=False` for development

### Authentication not working
- Ensure `AuthenticationMiddleware` is added to your server
- Check that endpoints use `@auth_endpoint` not `@endpoint` for protection

---

**Total setup time: ~5 minutes**

Your jvspatial API is now secured with enterprise-grade authentication!