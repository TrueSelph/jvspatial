# jvspatial Authentication Examples

This directory contains examples demonstrating authentication and authorization features in jvspatial.

## Features Demonstrated

- JWT token authentication
- API key authentication
- Role-based access control (RBAC)
- Permission-based endpoint protection
- User session management
- Secure configuration patterns

## Files

- `auth_example.py` - Complete example showing auth features
- `.env.example` - Template showing required configuration

## Running the Examples

1. Copy the environment template:
```bash
cp .env.example .env
```

2. Edit the `.env` file with your settings:
```bash
# Generate a secure secret key
JVSPATIAL_JWT_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))')
echo "JVSPATIAL_JWT_SECRET=$JVSPATIAL_JWT_SECRET" >> .env

# Generate some API keys
JVSPATIAL_API_KEYS=$(python -c 'import secrets; print(",".join(secrets.token_urlsafe(32) for _ in range(3)))')
echo "JVSPATIAL_API_KEYS=$JVSPATIAL_API_KEYS" >> .env
```

3. Run the example:
```bash
python auth_example.py
```

## Authentication Methods

### JWT Authentication

```python
from jvspatial.api.auth.decorators import auth_endpoint

@auth_endpoint("/api/secure", auth_required=True)
async def secure_endpoint(endpoint):
    """Endpoint requiring JWT auth."""
    user = get_current_user()
    return endpoint.success(data={"user": user.username})
```

### API Key Authentication

```python
from jvspatial.api.auth.decorators import auth_endpoint

@auth_endpoint("/api/key-auth", api_key_required=True)
async def api_key_endpoint(endpoint):
    """Endpoint requiring API key."""
    return endpoint.success(data={"status": "authenticated"})
```

### Role-Based Access Control

```python
@auth_endpoint(
    "/api/admin",
    auth_required=True,
    roles=["admin"]
)
async def admin_endpoint(endpoint):
    """Only admins can access this endpoint."""
    return endpoint.success(data={"access": "granted"})
```

### Permission-Based Access

```python
@auth_endpoint(
    "/api/documents",
    auth_required=True,
    permissions=["read_documents"]
)
async def read_documents(endpoint):
    """User must have read_documents permission."""
    return endpoint.success(data={"access": "granted"})
```

## Security Best Practices

1. Use environment variables for sensitive configuration
2. Generate strong secrets for JWT and API keys
3. Enable HTTPS in production
4. Set appropriate token expiration times
5. Use specific permissions instead of broad role checks
6. Implement proper error handling and logging
7. Use session caching for better performance

## API Documentation

When running the server, access the auto-generated API documentation:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

The documentation includes:
- Authentication requirements
- Required permissions and roles
- Request/response schemas
- Example requests

## Testing

Test the authenticated endpoints using curl:

```bash
# Get a JWT token
TOKEN=$(curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}' \
  | jq -r .access_token)

# Use the token
curl http://localhost:8000/api/secure \
  -H "Authorization: Bearer $TOKEN"

# Use an API key
curl http://localhost:8000/api/key-auth \
  -H "X-API-Key: your-api-key"
```

## Error Handling

The example demonstrates proper error handling:

```python
@auth_endpoint("/api/secure")
async def handle_errors(endpoint):
    try:
        # Your code here
        return endpoint.success(data={"status": "ok"})
    except UnauthorizedError:
        return endpoint.unauthorized(
            message="Invalid credentials",
            details={"required": ["valid_token"]}
        )
    except ForbiddenError:
        return endpoint.forbidden(
            message="Insufficient permissions",
            details={"required": ["admin"]}
        )
    except Exception as e:
        return endpoint.error(
            message="Internal error",
            status_code=500
        )
```