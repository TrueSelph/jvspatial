# jvspatial Authentication System

The jvspatial authentication system provides comprehensive user management, JWT-based sessions, API key authentication, and role-based access control (RBAC) that integrates seamlessly with the spatial data architecture.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Authentication Concepts](#authentication-concepts)
3. [Request State Contract](#request-state-contract)
4. [Configuration](#configuration)
5. [User Management](#user-management)
6. [JWT Authentication](#jwt-authentication)
7. [API Key Authentication](#api-key-authentication)
8. [Role-Based Access Control](#role-based-access-control)
9. [Spatial Permissions](#spatial-permissions)
10. [Endpoint Protection](#endpoint-protection)
11. [Middleware Integration](#middleware-integration)
12. [Security Best Practices](#security-best-practices)
13. [API Reference](#api-reference)

## Quick Start

Set up authentication in minutes using `Server(auth={...})`:

```python
from jvspatial.api import Server, endpoint

# Create server with authentication enabled (no configure_auth needed)
server = Server(
    title="My Authenticated API",
    description="Spatial API with authentication",
    version="1.0.0",
    db_type="json",
    db_path="./data",
    auth=dict(
        auth_enabled=True,
        jwt_secret="your-super-secret-key-change-in-production",
        jwt_expire_minutes=1440,  # 24 hours
    ),
)

@endpoint("/public/info")  # No authentication required
async def public_info():
    return {"message": "This is public"}

@endpoint("/protected/data", auth=True, permissions=["read_data"])
async def protected_data():
    return {"message": "This requires authentication and read_data permission"}

@endpoint("/admin/users", auth=True, roles=["admin"])
async def admin_users():
    return {"message": "Admin only"}

# Unified decorators work with Walker classes too
@endpoint("/admin/process", auth=True, roles=["admin"])
class AdminProcessor(Walker):
    pass

if __name__ == "__main__":
    server.run()
```

> **Note**: Use `Server(auth={...})` for configuration. The deprecated `configure_auth()` pattern is no longer recommended.

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

## Request State Contract

The authentication middleware uses `request.state.user` as the standard contract for passing authenticated user information to downstream handlers:

- **`request.state.user`** is set by `AuthenticationMiddleware` after successful authentication (JWT or API key).
- Endpoints receive `user_id` via the `@endpoint` decorator, which injects it from `request.state.user`. When `auth=True`, `user_id` is guaranteed non-None (401 is returned automatically if missing).
- Add `user_id: str` or `current_user` as a parameter to receive the injected value; no manual guard needed.
- **Pre-setting for tests**: When using ASGI in-process (e.g. `TestClient` or httpx `ASGITransport`), you may pre-set `request.state.user` before the middleware runs. The middleware will skip authentication if `user` is already set and has an `id` attribute. Set `auth=dict(test_mode=True, ...)` to explicitly enable this for test environments.

## Configuration

### Basic Configuration

Configure authentication via `Server(auth={...})`:

```python
from jvspatial.api import Server

server = Server(
    db_type="json",
    db_path="./data",
    auth=dict(
        auth_enabled=True,
        jwt_secret="your-256-bit-secret-key",
        jwt_algorithm="HS256",
        jwt_expire_minutes=1440,  # 24 hours
        refresh_expire_days=30,
        api_key_header="x-api-key",
        api_key_management_enabled=True,
    ),
)
```

### Bootstrap Admin (Env-Based)

Create an admin user on startup when no admin exists:

```python
import os

server = Server(
    db_type="json",
    db_path="./data",
    auth=dict(
        auth_enabled=True,
        jwt_secret="your-secret-key",
        bootstrap_admin_email=os.getenv("ADMIN_EMAIL"),
        bootstrap_admin_password=os.getenv("ADMIN_PASSWORD"),
        bootstrap_admin_name=os.getenv("ADMIN_NAME"),
    ),
    on_admin_bootstrapped=my_callback,  # Optional: called with UserResponse when admin created
)
```

When `bootstrap_admin_email` and `bootstrap_admin_password` are set, the server creates an admin on first run if none exists. Use `on_admin_bootstrapped` to create app-specific entities (e.g. UserNode) alongside the AuthUser.

### Callbacks for App-Specific Logic

```python
def on_admin_created(user_response):
    """Create UserNode when admin is bootstrapped."""
    # Create domain entities linked to AuthUser
    pass

async def on_user_registered(user_response, request_body):
    """Create UserNode, Organization, etc. after registration."""
    # request_body includes email, password, and any extra fields (name, organizationName, etc.)
    pass

async def enrich_current_user(user_response):
    """Augment /auth/me response with app-specific data."""
    return {"display_name": "...", "organization": {...}}

async def on_password_reset(email, token, reset_url):
    """Send password reset email. Called when user requests reset."""
    # reset_url is built from password_reset_base_url when configured
    await send_email(email, "Reset your password", f"Click: {reset_url}")

server = Server(
    auth=dict(auth_enabled=True, jwt_secret="...", password_reset_base_url="https://app.example.com"),
    on_admin_bootstrapped=on_admin_created,
    on_user_registered=on_user_registered,
    on_enrich_current_user=enrich_current_user,
    on_password_reset_requested=on_password_reset,
)
```

### Environment Variables

Set these in production:

```bash
# .env file
JVSPATIAL_JWT_SECRET_KEY="your-super-secret-256-bit-key"
JVSPATIAL_DB_PATH="./data"  # For JSON/SQLite when using env-only config

# Bootstrap admin (optional)
ADMIN_EMAIL="admin@example.com"
ADMIN_PASSWORD="secure-password"
ADMIN_NAME="Administrator"
```

### Database Context for Auth

Authentication (JWT and API key validation) **always uses the prime database** via `get_prime_database()`, regardless of `server._graph_context`. This ensures:

- Valid tokens succeed even when the server's graph context points at a different database (e.g. after `set_graph_context()` or multi-tenant switches)
- User lookup and session data are consistent with the database where users were created

If you see 401 with a valid token, ensure you are using jvspatial 0.0.5+ which includes this fix.

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

# Server automatically validates and injects user_id/current_user
@endpoint("/protected/data", auth=True)
async def get_data(user_id: str):
    return {"user_id": user_id, "data": "protected content"}

# Or receive the full user object
@endpoint("/protected/profile", auth=True)
async def get_profile(current_user):
    return {"user": current_user.email, "roles": current_user.roles}
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

### Token Validation Behavior

The authentication system validates JWT tokens using a decode-first approach:

**Validation Order:**
- Tokens are decoded first using `jwt.decode()`, which automatically handles expiration validation
- Only successfully decoded, non-expired tokens are checked against the blacklist
- This prevents false positives where expired tokens might be incorrectly flagged

**Expiration Handling:**
- Token expiration is handled by the `jwt.decode()` function, not manual timestamp checks
- Expired tokens are rejected during decode, before any blacklist checks occur
- This ensures consistent expiration validation across all token types

**Debug Logging:**
- Detailed debug logging is available for troubleshooting authentication issues
- Logs include: token decode results, blacklist check outcomes, user lookup results, and validation failures
- Enable debug logging to trace authentication flow and diagnose 401 errors

**Performance Optimization:**
- Blacklist checks use an in-memory cache to reduce database queries
- Cache entries have configurable TTL (time-to-live) for optimal performance
- Cache misses trigger database lookups and update the cache

### Refresh Token Generation

The system generates refresh tokens with resilience and reliability:

**Resilient Generation:**
- Login succeeds even if refresh token generation or storage fails
- Access tokens work independently of refresh tokens
- If refresh token generation fails, login returns `refresh_token=None` but the access token is still valid

**Automatic Index Management:**
- Indexes are automatically created before saving refresh tokens
- This ensures optimal database performance for token lookups
- The `ensure_indexes()` call happens transparently during token storage

**Token Storage:**
- Refresh tokens are hashed before storage using secure hashing algorithms (bcrypt, argon2, or passlib)
- Plaintext tokens are never stored in the database
- Token verification uses secure hash comparison

### API Endpoint Organization

Auth endpoints are mounted at `{prefix}/auth/...` where prefix defaults to `/api` and can be overridden via `JVSPATIAL_API_PREFIX`. See [Environment Configuration](environment-configuration.md) for details.

Endpoints are organized by tags in OpenAPI documentation:

**Tag Organization:**
- Authentication endpoints (`/api/auth/*`) are tagged as **"Auth"** in OpenAPI docs
- Application endpoints (`/api/graph`, `/api/logs`) are tagged as **"App"**
- Tags help organize and filter endpoints in Swagger UI

**Benefits:**
- Clear separation between authentication and application endpoints
- Easier navigation in API documentation
- Better organization for API consumers

## API Key Authentication

### Quick Start

```python
from jvspatial.api import Server

server = Server(
    title="My API",
    auth_enabled=True,  # Master switch - enables both JWT and API key auth
    api_key_management_enabled=True,  # Enable API key management endpoints (/auth/api-keys)
    db_type="json"
)
```

**Configuration Flags:**
- `auth_enabled`: Master switch that enables authentication middleware. When `True`:
  - JWT authentication is always available (via `Authorization: Bearer <token>` header)
  - API key authentication is always available (via `X-API-Key` header)
  - Both methods appear in Swagger/OpenAPI documentation
- `api_key_management_enabled`: Controls whether API key management endpoints (`/auth/api-keys`) are registered. Does NOT control whether API key authentication works - that's always available when `auth_enabled=True`.

### Creating API Keys

API keys are created through authenticated endpoints. First login to get a JWT token, then create keys:

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}'

# Create API key
curl -X POST http://localhost:8000/api/auth/api-keys \
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
@endpoint("/spatial/query", auth=True, permissions=["read_spatial_data"])
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
@endpoint("/nodes/process", auth=True)
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
@endpoint("/graph/traverse", auth=True)
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
@endpoint("/user/profile", auth=True)
async def user_profile():
    return {"message": "Must be logged in"}

@endpoint("/user/data", auth=True)
class UserData(Walker):
    pass

# 3. Permission-based endpoints (auto-detects functions/walkers)
@endpoint("/reports/generate", auth=True, permissions=["generate_reports"])
async def generate_report():
    return {"message": "Must have generate_reports permission"}

@endpoint("/spatial/analysis", auth=True, permissions=["analyze_spatial_data"])
class SpatialAnalysis(Walker):
    pass

# 4. Role-based endpoints (auto-detects functions/walkers)
@endpoint("/admin/settings", auth=True, roles=["admin"])
async def admin_settings():
    return {"message": "Must be admin"}

# 5. Admin-only endpoints (auto-detects functions/walkers)
@endpoint("/admin/users", auth=True, roles=["admin"])
async def manage_users():
    return {"message": "Admin access required"}

@endpoint("/admin/process", auth=True, roles=["admin"])
class AdminProcessor(Walker):
    pass
```

### Multiple Requirements

```python
# Require specific permissions AND roles
@endpoint(
    "/advanced/operation",
    auth=True,
    permissions=["advanced_operations", "write_data"],
    roles=["analyst", "admin"]
)
async def advanced_operation():
    # User must have BOTH permissions AND at least one of the roles
    pass
```

### Getting Current User in Endpoints

Use `user_id` or `current_user` parameters—they are injected automatically when `auth=True`:

```python
@endpoint("/user/dashboard", auth=True)
async def user_dashboard(user_id: str, current_user):
    return {
        "user": {
            "id": user_id,
            "email": current_user.email,
            "roles": current_user.roles,
            "permissions": current_user.permissions
        }
    }

@endpoint("/user/spatial-data", auth=True)
class UserSpatialData(Walker):
    @on_visit(Node)
    async def process(self, here: Node):
        # current_user is injected when auth=True
        pass
```

### get_auth_service

For custom auth logic (e.g. token validation, custom endpoints), use the shared auth service:

```python
from jvspatial.api import get_auth_service

auth_service = get_auth_service()
user = await auth_service.validate_token(token)
# Or: bootstrap_admin, register_user, login_user, etc.
```

Requires a Server with auth enabled. Raises `RuntimeError` if no server or auth not configured.

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

1. **Exempt Paths**: Paths in `exempt_paths` bypass authentication. Built-in auth paths (`/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/signup`, `/auth/forgot-password`, `/auth/reset-password`) are always exempt. **`/_internal/deferred`** (jvspatial deferred task / LWA pass-through) is **always** merged in as well—you cannot remove it via `exempt_paths`, because Lambda async invoke cannot send your app JWT. PathMatcher expands these using `APIRoutes.PREFIX` (default `/api`).
2. **Files HTTP routes** (`FileStorageService`): Registered under **`{JVSPATIAL_API_PREFIX}/files`** (default `/api/files`). **`POST .../files/upload`**, **`DELETE .../files/{path}`**, and proxy admin routes under **`.../files/proxy`** require JWT or API key when auth is enabled. **`GET .../files/{path}`** is **public by default**; set **`JVSPATIAL_FILES_PUBLIC_READ=false`** to require authentication for direct reads. **`GET {JVSPATIAL_PROXY_PREFIX}/{code}`** (default `/p/{code}`) is explicitly public—the proxy code is the credential. For anonymous direct file URLs when public read is off, use proxy links or add a **narrow** `exempt_paths` pattern only after security review (patterns are path-only, not per HTTP method).
3. **Registered Endpoints**: Endpoints in the registry with `auth=False` are public
4. **Unknown Endpoints**: Endpoints not in the registry **require authentication**
5. **Error Handling**: Any error during authentication checking **denies access**

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

**Note**: Exempt paths are checked **before** registry lookups, so they bypass authentication entirely. Use exempt paths for system routes like health checks and documentation. Use prefix-relative paths (e.g. `/auth/login`) when customizing `exempt_paths`. Avoid hardcoding `/api`—PathMatcher expands paths using `JVSPATIAL_API_PREFIX` at runtime.

## Security Best Practices

### Production Configuration

```python
# Use secure settings in production via Server(auth={...})
server = Server(
    db_type="json",
    db_path="./data",
    auth=dict(
        auth_enabled=True,
        jwt_secret=os.getenv("JVSPATIAL_JWT_SECRET_KEY"),  # 256-bit random key
        jwt_algorithm="HS256",
        jwt_expire_minutes=1440,
    ),
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
- `POST /auth/register` - User registration (accepts extra fields; pass to `on_user_registered` callback)
- `POST /auth/login` - User login
- `POST /auth/refresh` - Token refresh
- `POST /auth/logout` - User logout
- `POST /auth/forgot-password` - Request password reset (always returns success; no email enumeration). Requires `on_password_reset_requested` callback to send the reset email; otherwise the token is created but no email is sent.
- `POST /auth/reset-password` - Complete password reset with token from email

**Authenticated Endpoints:**
- `GET /auth/me` - Get current user (supports `on_enrich_current_user` callback)
- `POST /auth/change-password` - Change password (requires current password verification)
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
# Import decorator
from jvspatial.api import endpoint

# Usage patterns - work with both functions and Walker classes
# Authenticated endpoint
@endpoint("/path", auth=True, methods=["GET"], permissions=["perm"], roles=["role"])
async def auth_function():
    pass

@endpoint("/path", auth=True, permissions=["perm"], roles=["role"])
class AuthWalker(Walker):
    pass

# Admin-only endpoint
@endpoint("/admin/path", auth=True, roles=["admin"], methods=["GET"])
async def admin_function():
    pass

@endpoint("/admin/path", auth=True, roles=["admin"])
class AdminWalker(Walker):
    pass
```

### Utility Functions

```python
from jvspatial.api import get_auth_service

# Get the configured AuthenticationService (for custom endpoints, token validation)
auth_service = get_auth_service()
user = await auth_service.validate_token(token)
```

For endpoints: use `user_id` or `current_user` parameters—injected from `request.state.user` when `auth=True`.

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
@endpoint("/data", auth=True, permissions=["read_data"])
async def get_data():
    return {"data": "authenticated users with read_data permission"}
```

### Setting Up Authentication

```python
# Step 1: Create server with auth config (middleware is added automatically)
server = Server(
    db_type="json",
    db_path="./data",
    auth=dict(auth_enabled=True, jwt_secret="your-secret-key"),
)

# Step 2: Use endpoint decorators with auth parameters
# Public endpoints: @endpoint("/path") - no auth required
# Protected endpoints: @endpoint("/path", auth=True) - requires authentication
# Admin endpoints: @endpoint("/path", auth=True, roles=["admin"]) - requires admin role
```

## See Also

- [Authentication Examples](../examples/api/authenticated_endpoints_example.py) - Complete working examples
- [REST API Integration](rest-api.md) - API endpoint patterns
- [Server API Documentation](server-api.md) - Server configuration
- [Security Quickstart](auth-quickstart.md) - Get started quickly

---

**[← Back to README](../../README.md)** | **[Authentication Examples →](../examples/api/authenticated_endpoints_example.py)**