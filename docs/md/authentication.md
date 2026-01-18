# jvspatial Authentication System

The jvspatial authentication system provides comprehensive user management, JWT-based sessions, API key authentication, and role-based access control (RBAC) that integrates seamlessly with the spatial data architecture.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Authentication Concepts](#authentication-concepts)
3. [Configuration](#configuration)
4. [User Management](#user-management)
5. [JWT Authentication](#jwt-authentication)
6. [API Key Authentication](#api-key-authentication)
7. [Role-Based Access Control](#role-based-access-control)
8. [Spatial Permissions](#spatial-permissions)
9. [Endpoint Protection](#endpoint-protection)
10. [Middleware Integration](#middleware-integration)
11. [Security Best Practices](#security-best-practices)
12. [API Reference](#api-reference)

## Quick Start

Set up authentication in minutes:

```python
from jvspatial.api import create_server, endpoint, auth_endpoint, admin_endpoint
from jvspatial.api.auth import configure_auth, AuthenticationMiddleware

# Configure authentication
configure_auth(
    jwt_secret_key="your-super-secret-key-change-in-production",
    jwt_expiration_hours=24,
    rate_limit_enabled=True
)

# Create server
server = create_server(
    title="My Authenticated API",
    description="Spatial API with authentication",
    version="1.0.0"
)

# Add authentication middleware
server.app.add_middleware(AuthenticationMiddleware)

@endpoint("/public/info")  # No authentication required
async def public_info():
    return {"message": "This is public"}

@auth_endpoint("/protected/data", permissions=["read_data"])
async def protected_data():
    return {"message": "This requires authentication and read_data permission"}

@admin_endpoint("/admin/users")
async def admin_users():
    return {"message": "Admin only"}

# Unified decorators work with Walker classes too
@admin_endpoint("/admin/process")
class AdminProcessor(Walker):
    pass

if __name__ == "__main__":
    server.run()
```

## Authentication Concepts

The jvspatial authentication system is built around several key concepts:

### 1. Users
Users are the primary actors in the system, stored in a separate `user` collection for security isolation:

```python
from jvspatial.api.auth import User

# Users have spatial-aware permissions
class User(Object):
    email: str
    password_hash: str  # BCrypt hashed

    # User status
    is_active: bool = True
    is_verified: bool = False
    is_admin: bool = False

    # Spatial permissions
    allowed_regions: List[str] = []  # Region IDs user can access
    allowed_node_types: List[str] = []  # Node types user can interact with
    max_traversal_depth: int = 10  # Graph traversal limit

    # RBAC
    roles: List[str] = ["user"]
    permissions: List[str] = []
```

### 2. Sessions
JWT-based sessions provide secure, stateless authentication:

```python
# Session management
session = await Session.create(
    session_id="unique-session-id",
    user_id=user.id,
    jwt_token="eyJ...",  # Access token
    refresh_token="eyJ...",  # Refresh token
    expires_at=datetime.now() + timedelta(hours=24)
)
```

### 3. API Keys
Long-lived tokens for service-to-service authentication:

```python
# API keys for automated systems
api_key = await APIKey.create(
    name="Production Service",
    key_id="prod-service-key",
    key_hash="hashed-secret-key",
    allowed_endpoints=["/api/data/*"],
    rate_limit_per_hour=10000
)
```

## Configuration

### Basic Configuration

```python
from jvspatial.api.auth import configure_auth

configure_auth(
    # JWT Settings
    jwt_secret_key="your-256-bit-secret-key",
    jwt_algorithm="HS256",
    jwt_expiration_hours=24,
    jwt_refresh_expiration_days=30,

    # API Key Settings
    api_key_header="X-API-Key",
    api_key_query_param="api_key",

    # Rate Limiting
    rate_limit_enabled=True,
    default_rate_limit_per_hour=1000,

    # Security
    require_https=True,  # Production setting
    session_cookie_secure=True,  # Production setting
    session_cookie_httponly=True
)
```

### Environment Variables

Set these in production:

```bash
# .env file
JVSPATIAL_JWT_SECRET_KEY="your-super-secret-256-bit-key"
JVSPATIAL_JWT_EXPIRATION_HOURS=24
JVSPATIAL_REQUIRE_HTTPS=true
JVSPATIAL_RATE_LIMIT_ENABLED=true
```

## User Management

### User Registration

```python
@endpoint("/auth/register", methods=["POST"])
async def register_user(request: UserRegistrationRequest):
    # Built-in endpoint handles:
    # - Password validation
    # - Duplicate email checks
    # - Secure password hashing
    # - User creation
    pass
```

### User Authentication

```python
from jvspatial.api.auth import authenticate_user

# Authenticate with email and password
user = await authenticate_user("alice@example.com", "password123")

# Check user permissions
if user.has_permission("read_spatial_data"):
    # User can read spatial data
    pass

if user.has_role("admin"):
    # User is an admin
    pass
```

### Spatial User Permissions

Users can be restricted to specific spatial regions and node types:

```python
# Create user with spatial restrictions
user = await User.create(
    email="regional_analyst@example.com",
    password_hash=User.hash_password("password"),
    allowed_regions=["us-west", "us-east"],  # Only these regions
    allowed_node_types=["City", "Highway"],  # Only these node types
    max_traversal_depth=5  # Limited graph traversal
)

# Check spatial permissions
if user.can_access_region("us-west"):
    # User can access US West region
    pass

if user.can_access_node_type("City"):
    # User can interact with City nodes
    pass
```

## JWT Authentication

### Token Structure

```python
# Access Token Payload
{
    "sub": "user_id",
    "email": "alice@example.com",
    "roles": ["user", "analyst"],
    "is_admin": false,
    "exp": 1640995200,  # Expiration timestamp
    "iat": 1640908800,  # Issued at timestamp
    "type": "access"
}

# Refresh Token Payload (minimal)
{
    "sub": "user_id",
    "exp": 1643500800,
    "iat": 1640908800,
    "type": "refresh"
}
```

### Using JWT Tokens

```python
# Client sends token in Authorization header
headers = {
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}

# Server automatically validates and extracts user context
from jvspatial.api.auth import get_current_user

@auth_endpoint("/protected/data")
async def get_data(request: Request):
    current_user = get_current_user(request)
    return {"user": current_user.email, "data": "protected content"}
```

### Token Refresh

```python
@endpoint("/auth/refresh", methods=["POST"])
async def refresh_token(request: TokenRefreshRequest):
    # Built-in endpoint handles:
    # - Refresh token validation
    # - New access token generation
    # - Session updates
    pass
```

## API Key Authentication

### Quick Start

```python
from jvspatial.api import Server

server = Server(
    title="My API",
    auth_enabled=True,
    api_key_auth_enabled=True,  # Enable API key authentication
    db_type="json"
)
```

### Creating API Keys

API keys are created through authenticated endpoints. First login to get a JWT token, then create keys:

```bash
# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}'

# Create API key
curl -X POST http://localhost:8000/auth/api-keys \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production Key",
    "permissions": ["read", "write"],
    "rate_limit_override": 1000,
    "expires_in_days": 90
  }'
```

**Response (shown ONCE only):**
```json
{
  "key": "sk_live_abc123...xyz789",
  "key_id": "k:APIKey:uuid",
  "key_prefix": "sk_live_abc12345",
  "name": "Production Key",
  "message": "Store this key securely. It won't be shown again."
}
```

### Using API Keys

Include the API key in the `X-API-Key` header:

```python
import requests

headers = {"X-API-Key": "sk_live_abc123...xyz789"}
response = requests.get("http://localhost:8000/api/data", headers=headers)
```

### API Key Management

- **List Keys**: `GET /auth/api-keys` (requires JWT authentication)
- **Revoke Key**: `DELETE /auth/api-keys/{key_id}` (requires JWT authentication)

### Security Features

- **Hashed Storage**: Keys are hashed (SHA-256) before storage, never stored in plaintext
- **IP Restrictions**: Whitelist specific IP addresses
- **Endpoint Restrictions**: Limit keys to specific API endpoints
- **Expiration**: Optional expiration dates
- **Per-Key Rate Limits**: Custom rate limits per key

📖 **[Complete API Keys Guide →](api-keys.md)**

## Role-Based Access Control

### Default Roles

The system includes standard roles:

- `user` - Basic authenticated user
- `admin` - System administrator
- `superuser` - Full system access

### Custom Roles and Permissions

```python
# Create user with custom roles and permissions
user = await User.create(
    email="spatial_analyst@example.com",
    roles=["analyst", "data_viewer"],
    permissions=[
        "read_spatial_data",
        "write_spatial_data",
        "export_reports",
        "access_analytics"
    ]
)

# Check permissions
if user.has_permission("read_spatial_data"):
    # Allow spatial data access
    pass

if user.has_role("analyst"):
    # Allow analyst features
    pass
```

### Permission Inheritance

```python
# Admin users automatically have all permissions
admin_user = await User.create(
    email="admin@example.com",
    is_admin=True,
    roles=["admin"]  # Admin role also grants all permissions
)

# Check: admin_user.has_permission("any_permission") returns True
```

## Spatial Permissions

### Region-Based Access

```python
# Restrict user to specific spatial regions
user.allowed_regions = ["north_america", "europe"]

# In spatial queries, check region access
@auth_endpoint("/spatial/query", permissions=["read_spatial_data"])
class SpatialQuery(Walker):
    region: str = EndpointField(description="Target region")

    @on_visit(Node)
    async def process(self, here: Node):
        current_user = get_current_user(self.request)

        if not current_user.can_access_region(self.region):
            raise HTTPException(403, "Access denied to this region")

        # Process spatial query...
```

### Node Type Restrictions

```python
# Restrict user to specific node types
user.allowed_node_types = ["City", "Highway", "POI"]

# Validate node type access in walkers
@auth_endpoint("/nodes/process")
class ProcessNodes(Walker):
    @on_visit(Node)
    async def process(self, here: Node):
        current_user = get_current_user(self.request)
        node_type = here.__class__.__name__

        if not current_user.can_access_node_type(node_type):
            return  # Skip this node

        # Process allowed node types...
```

### Traversal Depth Limits

```python
# Limit graph traversal depth for users
@auth_endpoint("/graph/traverse")
class GraphTraversal(Walker):
    max_depth: int = EndpointField(default=5)

    @on_visit(Node)
    async def traverse(self, here: Node):
        current_user = get_current_user(self.request)

        # Enforce user's traversal limit
        actual_max = min(self.max_depth, current_user.max_traversal_depth)

        # Use actual_max for traversal...
```

## Endpoint Protection

### Protection Levels

```python
# 1. Public endpoints (no authentication)
@endpoint("/public/info")
async def public_info():
    return {"message": "Anyone can access this"}

@endpoint("/public/search")
class PublicSearch(Walker):
    pass

# 2. Authenticated endpoints (login required, auto-detects functions/walkers)
@auth_endpoint("/user/profile")
async def user_profile():
    return {"message": "Must be logged in"}

@auth_endpoint("/user/data")
class UserData(Walker):
    pass

# 3. Permission-based endpoints (auto-detects functions/walkers)
@auth_endpoint("/reports/generate", permissions=["generate_reports"])
async def generate_report():
    return {"message": "Must have generate_reports permission"}

@auth_endpoint("/spatial/analysis", permissions=["analyze_spatial_data"])
class SpatialAnalysis(Walker):
    pass

# 4. Role-based endpoints (auto-detects functions/walkers)
@auth_endpoint("/admin/settings", roles=["admin"])
async def admin_settings():
    return {"message": "Must be admin"}

# 5. Admin-only endpoints (shortcut, auto-detects functions/walkers)
@admin_endpoint("/admin/users")
async def manage_users():
    return {"message": "Admin access required"}

@admin_endpoint("/admin/process")
class AdminProcessor(Walker):
    pass
```

### Multiple Requirements

```python
# Require specific permissions AND roles
@auth_endpoint(
    "/advanced/operation",
    permissions=["advanced_operations", "write_data"],
    roles=["analyst", "admin"]
)
async def advanced_operation():
    # User must have BOTH permissions AND at least one of the roles
    pass
```

### Getting Current User in Endpoints

```python
from jvspatial.api.auth import get_current_user

@auth_endpoint("/user/dashboard")
async def user_dashboard(request: Request):
    current_user = get_current_user(request)

    return {
        "user": {
            "email": current_user.email,
            "roles": current_user.roles,
            "permissions": current_user.permissions
        }
    }

@auth_endpoint("/user/spatial-data")
class UserSpatialData(Walker):
    @on_visit(Node)
    async def process(self, here: Node):
        current_user = get_current_user(self.request)

        # Use current_user for access control
        if current_user.can_access_node_type(here.__class__.__name__):
            self.response["nodes"].append(await here.export())
```

## Middleware Integration

### Adding Authentication Middleware

```python
from jvspatial.api.auth import AuthenticationMiddleware

# Add to server (recommended)
server = create_server(title="My API")
server.app.add_middleware(AuthenticationMiddleware)

# Or add to FastAPI app directly
app = FastAPI()
app.add_middleware(AuthenticationMiddleware)
```

### Middleware Features

The `AuthenticationMiddleware` automatically:

- **Validates JWT tokens** from Authorization headers
- **Validates API keys** from headers or query parameters
- **Enforces rate limits** per user/key
- **Injects user context** into requests
- **Handles authentication errors** with proper HTTP responses
- **Exempts public endpoints** from authentication

### Registry-Based Authentication

The authentication middleware uses the **endpoint registry** as the single source of truth for authentication decisions:

1. **Registered Endpoints**: All endpoints registered via the `@endpoint` decorator are tracked in the endpoint registry
2. **Auth Settings**: The `auth` parameter in `@endpoint` determines whether authentication is required:
   - `auth=True`: Endpoint requires authentication
   - `auth=False`: Endpoint is public (no authentication required)
   - Default: `auth=False` (endpoints are public by default)
3. **Unregistered Endpoints**: Endpoints not in the registry **require authentication by default** (deny by default security model)

**Important**: Only endpoints explicitly registered with `auth=False` are public. This ensures that:
- Dynamically registered endpoints (e.g., from extended applications) respect their `auth` settings
- Public endpoints with `auth=False` are accessible without authentication
- The authentication behavior is consistent across all registered endpoints
- Unknown endpoints are protected by default, preventing security vulnerabilities

### Security Model: Deny By Default

The authentication middleware follows a **"deny by default"** security model:

1. **Exempt Paths**: Only paths explicitly listed in `exempt_paths` bypass authentication
2. **Registered Endpoints**: Endpoints in the registry with `auth=False` are public
3. **Unknown Endpoints**: Endpoints not in the registry **require authentication**
4. **Error Handling**: Any error during authentication checking **denies access**

This approach ensures that:
- Path matching failures don't create security vulnerabilities
- New endpoints are protected by default until explicitly configured
- Configuration errors fail securely (deny access rather than allow)
- Bypass attempts via path manipulation are blocked

**Important**: All non-authenticated endpoints must either:
- Be listed in `exempt_paths` configuration, OR
- Be registered with `@endpoint(..., auth=False)`

Unregistered endpoints will require authentication regardless of intent.

### Configuring Exemptions

```python
# Middleware automatically exempts these paths:
exempted_paths = [
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/auth/login",
    "/auth/register",
    "/public/*"  # All public endpoints
]

# Custom exemption patterns can be added in middleware configuration
```

**Note**: Exempt paths are checked **before** registry lookups, so they bypass authentication entirely. Use exempt paths for system routes like health checks and documentation.

## Security Best Practices

### Production Configuration

```python
# Use secure settings in production
configure_auth(
    jwt_secret_key=os.getenv("JWT_SECRET_KEY"),  # 256-bit random key
    jwt_algorithm="HS256",
    require_https=True,
    session_cookie_secure=True,
    session_cookie_httponly=True,
    rate_limit_enabled=True
)
```

### Password Security

```python
# Strong password requirements
class UserRegistrationRequest(BaseModel):
    password: str = Field(
        ...,
        min_length=8,
        regex=r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]"
    )
```

### Rate Limiting

```python
# Configure rate limits by user type
standard_user_limit = 1000  # per hour
premium_user_limit = 5000   # per hour
admin_user_limit = 10000    # per hour

# Rate limiting is automatic based on user settings
user.rate_limit_per_hour = premium_user_limit
await user.save()
```

### API Key Security

```python
# Create API keys with limited scope
api_key = await APIKey.create(
    name="Data Export Service",
    allowed_endpoints=["/api/export/*"],  # Restrict endpoints
    rate_limit_per_hour=100,  # Lower limit for service
    expires_at=datetime.now() + timedelta(days=90)  # Expiration
)
```

## API Reference

### Built-in Authentication Endpoints

All authentication endpoints are automatically registered:

**Public Endpoints:**
- `POST /auth/register` - User registration
- `POST /auth/login` - User login
- `POST /auth/refresh` - Token refresh
- `POST /auth/logout` - User logout

**Authenticated Endpoints:**
- `GET /auth/profile` - Get user profile
- `PUT /auth/profile` - Update user profile
- `POST /auth/api-keys` - Create API key
- `GET /auth/api-keys` - List API keys
- `DELETE /auth/api-keys/{key_id}` - Revoke API key

**Admin Endpoints:**
- `GET /auth/admin/users` - List all users
- `PUT /auth/admin/users/{user_id}` - Update user
- `DELETE /auth/admin/users/{user_id}` - Delete user
- `GET /auth/admin/sessions` - List active sessions
- `DELETE /auth/admin/sessions/{session_id}` - Revoke session

### Authentication Decorators

```python
# Import decorators
from jvspatial.api.auth import (
    auth_endpoint,          # Unified authenticated endpoint (auto-detects functions/walkers)
    admin_endpoint,         # Unified admin endpoint (auto-detects functions/walkers)
    webhook_endpoint        # Unified webhook endpoint (auto-detects functions/walkers)
)

# Usage patterns - work with both functions and Walker classes
@auth_endpoint("/path", methods=["GET"], permissions=["perm"], roles=["role"])
async def auth_function():
    pass

@auth_endpoint("/path", permissions=["perm"], roles=["role"])
class AuthWalker(Walker):
    pass

@admin_endpoint("/admin/path", methods=["GET"])
async def admin_function():
    pass

@admin_endpoint("/admin/path")
class AdminWalker(Walker):
    pass
```

### Utility Functions

```python
from jvspatial.api.auth import (
    configure_auth,         # Configure authentication settings
    get_current_user,       # Get current user from request
    authenticate_user,      # Authenticate email/password
    create_user_session,    # Create user session
    refresh_session         # Refresh user session
)
```

### Exceptions

```python
from jvspatial.api.auth import (
    AuthenticationError,    # Base authentication error
    AuthorizationError,     # Permission/role error
    RateLimitError,        # Rate limit exceeded
    InvalidCredentialsError, # Bad email/password
    UserNotFoundError,      # User doesn't exist
    SessionExpiredError,    # Token expired
    APIKeyInvalidError      # Invalid API key
)
```

## Adding Authentication

### Protecting Endpoints

```python
# Public endpoint (anyone can access)
@endpoint("/data")
async def get_data():
    return {"data": "anyone can access"}

# Protected endpoint (requires authentication and permissions)
@auth_endpoint("/data", permissions=["read_data"])
async def get_data():
    return {"data": "authenticated users with read_data permission"}
```

### Setting Up Authentication

```python
# Step 1: Configure authentication
configure_auth(jwt_secret_key="your-secret-key")

# Step 2: Add middleware
server.app.add_middleware(AuthenticationMiddleware)

# Step 3: Update endpoint decorators as needed
# Public endpoints: Keep @endpoint (works with both functions and walkers)
# Protected endpoints: Change to @auth_endpoint (works with both functions and walkers)
# Admin endpoints: Change to @admin_endpoint (works with both functions and walkers)
```

## See Also

- [Authentication Examples](../examples/auth_demo.py) - Complete working examples
- [REST API Integration](rest-api.md) - API endpoint patterns
- [Server API Documentation](server-api.md) - Server configuration
- [Security Quickstart](auth-quickstart.md) - Get started quickly

---

**[← Back to README](../../README.md)** | **[Authentication Examples →](../examples/auth_demo.py)**