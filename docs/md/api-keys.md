# API Key Authentication

jvspatial provides comprehensive API key authentication for programmatic access to your API. API keys are stored securely in the database with hashing, support expiration, IP restrictions, and per-key rate limits.

## Overview

API keys are an alternative to JWT tokens for authentication, ideal for:
- Server-to-server communication
- Long-lived access without token refresh
- Service integrations
- Automated scripts and tools

## Features

- **Secure Storage**: Keys are hashed (SHA-256) before storage, never stored in plaintext
- **One-Time Display**: Full key shown only once on creation
- **Expiration Support**: Optional expiration dates for keys
- **IP Restrictions**: Whitelist specific IP addresses
- **Endpoint Restrictions**: Limit keys to specific API endpoints
- **Per-Key Rate Limits**: Custom rate limits per key
- **Permissions**: Grant specific permissions to keys

## Configuration

Enable API key authentication in your server configuration:

```python
from jvspatial.api import Server

server = Server(
    title="My API",
    auth_enabled=True,  # Master switch - enables both JWT and API key auth
    api_key_management_enabled=True,  # Enable API key management endpoints (/auth/api-keys)
    api_key_prefix="sk_",  # Optional: custom prefix
    db_type="json"
)
```

**Important Notes:**
- `auth_enabled=True` automatically enables both JWT and API key authentication
- API key authentication is always available when `auth_enabled=True` (middleware checks for X-API-Key header)
- `api_key_management_enabled` only controls whether the `/auth/api-keys` endpoints are registered
- Both authentication methods appear in Swagger/OpenAPI docs when `auth_enabled=True`

## Creating API Keys

API keys are created through authenticated endpoints. You must first register and login to get a JWT token, then use that token to create API keys.

### Create an API Key

```bash
# First, login to get a JWT token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "password123"
  }'

# Response:
# {
#   "access_token": "eyJ...",
#   "token_type": "bearer",
#   "expires_in": 1800,
#   "user": {...}
# }

# Create an API key
curl -X POST http://localhost:8000/auth/api-keys \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production Key",
    "permissions": ["read", "write"],
    "rate_limit_override": 100,
    "expires_in_days": 90,
    "allowed_ips": ["192.168.1.1"],
    "allowed_endpoints": ["/api/data", "/api/reports"]
  }'
```

**Response (ONE TIME ONLY):**
```json
{
  "key": "sk_live_abc123...xyz789",
  "key_id": "k:APIKey:uuid",
  "key_prefix": "sk_live_abc12345",
  "name": "Production Key",
  "message": "Store this key securely. It won't be shown again."
}
```

⚠️ **Important**: The full key is shown only once. Store it securely immediately. If lost, you must revoke and create a new key.

### Request Parameters

- `name` (required): Descriptive name for the key
- `permissions` (optional): List of permissions (e.g., `["read", "write"]`)
- `rate_limit_override` (optional): Custom rate limit in requests per minute
- `expires_in_days` (optional): Number of days until expiration (None = no expiration)
- `allowed_ips` (optional): List of allowed IP addresses (empty = all IPs)
- `allowed_endpoints` (optional): List of allowed endpoint prefixes (empty = all endpoints)

## Using API Keys

Include the API key in the `X-API-Key` header (or custom header configured in `api_key_header`):

```bash
curl http://localhost:8000/api/protected \
  -H "X-API-Key: sk_live_abc123...xyz789"
```

### Python Example

```python
import requests

headers = {
    "X-API-Key": "sk_live_abc123...xyz789"
}

response = requests.get("http://localhost:8000/api/data", headers=headers)
print(response.json())
```

## Managing API Keys

### List Your API Keys

```bash
curl http://localhost:8000/auth/api-keys \
  -H "Authorization: Bearer <jwt_token>"
```

**Response:**
```json
[
  {
    "id": "k:APIKey:uuid1",
    "name": "Production Key",
    "key_prefix": "sk_live_abc12345",
    "created_at": "2024-01-15T10:00:00Z",
    "last_used_at": "2024-01-20T14:30:00Z",
    "expires_at": "2024-04-15T10:00:00Z",
    "is_active": true,
    "permissions": ["read", "write"],
    "rate_limit_override": 100
  },
  {
    "id": "k:APIKey:uuid2",
    "name": "Development Key",
    "key_prefix": "sk_test_def67890",
    "created_at": "2024-01-10T08:00:00Z",
    "last_used_at": null,
    "expires_at": null,
    "is_active": true,
    "permissions": ["read"],
    "rate_limit_override": null
  }
]
```

### Revoke an API Key

```bash
curl -X DELETE http://localhost:8000/auth/api-keys/{key_id} \
  -H "Authorization: Bearer <jwt_token>"
```

**Response:**
```json
{
  "message": "API key revoked successfully"
}
```

## Security Features

### IP Restrictions

Limit API keys to specific IP addresses:

```python
# Create key with IP restriction
response = requests.post(
    "http://localhost:8000/auth/api-keys",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "name": "Office Key",
        "allowed_ips": ["203.0.113.0", "198.51.100.0"]
    }
)
```

Requests from other IPs will be rejected with 401 Unauthorized.

### Endpoint Restrictions

Limit API keys to specific endpoints:

```python
response = requests.post(
    "http://localhost:8000/auth/api-keys",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "name": "Read-Only Key",
        "allowed_endpoints": ["/api/data", "/api/reports"]
    }
)
```

The key can only access endpoints that start with the specified prefixes.

### Expiration

Set expiration dates for temporary access:

```python
response = requests.post(
    "http://localhost:8000/auth/api-keys",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "name": "Temporary Key",
        "expires_in_days": 30  # Expires in 30 days
    }
)
```

Expired keys are automatically rejected.

### Per-Key Rate Limits

Override default rate limits for specific keys:

```python
response = requests.post(
    "http://localhost:8000/auth/api-keys",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "name": "Premium Key",
        "rate_limit_override": 1000  # 1000 requests per minute
    }
)
```

## Best Practices

1. **Store Keys Securely**: Never commit API keys to version control
2. **Use Environment Variables**: Store keys in environment variables or secret managers
3. **Rotate Regularly**: Revoke and recreate keys periodically
4. **Use Descriptive Names**: Name keys based on their purpose (e.g., "Production Server", "CI/CD Pipeline")
5. **Set Expiration**: Use expiration dates for temporary access
6. **Restrict IPs**: Use IP restrictions for server-to-server communication
7. **Minimize Permissions**: Grant only necessary permissions
8. **Monitor Usage**: Check `last_used_at` to identify unused keys

## Key Format

API keys follow this format:
- Prefix: `sk_` (configurable via `api_key_prefix`)
- Type: `live_` or `test_` (optional, for organization)
- Random: 32+ character random string

Example: `sk_live_` followed by a 32+ character random string

The `key_prefix` shown in listings is the first 20 characters for identification without revealing the full key.

## Troubleshooting

### "Invalid API key" Error

- Verify the key is correct (no extra spaces)
- Check if the key has been revoked (`is_active: false`)
- Verify the key hasn't expired
- Ensure IP restrictions allow your current IP

### "Endpoint not allowed" Error

- Check `allowed_endpoints` for the key
- Verify the request path matches one of the allowed prefixes

### Key Not Found After Creation

- The full key is only shown once on creation
- If lost, you must revoke the old key and create a new one
- Use the `key_prefix` to identify keys in listings

## Integration with Rate Limiting

API keys work seamlessly with rate limiting:

- Keys with `rate_limit_override` use their custom limit
- Other keys use the default or endpoint-specific limits
- Rate limits are tracked per key (not per IP when using API keys)

See [Rate Limiting Guide](rate-limiting.md) for details.

## See Also

- [Authentication Guide](authentication.md) - General authentication overview
- [Rate Limiting Guide](rate-limiting.md) - Rate limiting configuration
- [REST API Guide](rest-api.md) - API endpoint documentation
