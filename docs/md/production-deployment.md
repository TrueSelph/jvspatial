# Production Deployment Guide

This guide covers essential configuration and security considerations for deploying jvspatial applications to production.

## Production Checklist

### 1. JWT Secret (Required when auth is enabled)

**Critical:** When authentication is enabled, you MUST set a secure JWT secret. The server will fail to start if you use the default placeholder.

```bash
# Generate a secure secret (32+ characters recommended)
export JVSPATIAL_JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

Or in your `.env`:

```
JVSPATIAL_JWT_SECRET_KEY=your-cryptographically-secure-secret-minimum-32-chars
```

**Never** use placeholder values like `your-secret-key` or `jvspatial-secret-key-change-in-production` in production.

### 2. Rate Limiting

Rate limiting is **disabled by default**. For production, enable it to protect against brute-force attacks and DoS. **Especially important** when using forgot-password: enable rate limiting to prevent abuse of the public `/auth/forgot-password` endpoint.

```python
server = Server(
    title="My API",
    auth_enabled=True,
    rate_limit=dict(
        rate_limit_enabled=True,
        rate_limit_default_requests=100,
        rate_limit_default_window=60,
    ),
)
```

Or via environment:

```
JVSPATIAL_RATE_LIMIT_ENABLED=true
```

### 3. Security Headers

Security headers (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection) are **enabled by default**. They are applied automatically. To disable (not recommended):

```python
server = Server(security=dict(security_headers_enabled=False))
```

### 4. CORS Configuration

The default CORS configuration allows localhost origins. For production, restrict to your actual frontend domain(s):

```python
server = Server(
    cors=dict(
        cors_origins=["https://app.example.com", "https://admin.example.com"],
        cors_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        cors_headers=["Authorization", "Content-Type", "X-API-Key"],
    ),
)
```

Avoid using `["*"]` for origins in production.

### 5. Database Configuration

- Use a production-grade backend (MongoDB, SQLite with proper path) rather than JSON for multi-instance deployments
- Ensure connection strings and credentials are loaded from environment variables or a secrets manager
- Configure connection pooling appropriately for your workload

### 6. HTTPS

- Serve the API over HTTPS in production
- Set `JVSPATIAL_WEBHOOK_HTTPS_REQUIRED=true` when using webhooks
- Use a reverse proxy (nginx, Caddy) or load balancer for TLS termination

### 7. Webhook HMAC Secret

When using webhooks, set a unique HMAC secret per environment:

```
JVSPATIAL_WEBHOOK_HMAC_SECRET=your-webhook-secret-minimum-32-chars
```

### 8. Logging

- Set `JVSPATIAL_LOG_LEVEL=info` or `warning` in production (avoid `debug`)
- Set `JVSPATIAL_DEBUG=false`
- Configure database logging for ERROR/CRITICAL if you need audit trails

## Environment Variables Summary

| Variable | Production Recommendation |
|----------|---------------------------|
| `JVSPATIAL_JWT_SECRET_KEY` | **Required** - cryptographically secure, 32+ chars |
| `JVSPATIAL_RATE_LIMIT_ENABLED` | `true` |
| `JVSPATIAL_DEBUG` | `false` |
| `JVSPATIAL_LOG_LEVEL` | `info` or `warning` |
| `JVSPATIAL_CORS_ORIGINS` | Your frontend domain(s), not `*` |
| `JVSPATIAL_WEBHOOK_HMAC_SECRET` | Unique per environment, 32+ chars |
| `JVSPATIAL_WEBHOOK_HTTPS_REQUIRED` | `true` |

## Kubernetes / Container Deployment

- Use Kubernetes secrets or external secrets operators for sensitive values
- Configure liveness/readiness probes using `/health`
- Set resource limits based on your workload
- Consider horizontal pod autoscaling with shared cache (Redis) and database

## See Also

- [Environment Configuration](environment-configuration.md) - Full variable reference
- [Authentication Guide](authentication.md) - Auth setup and API keys
- [Server API](server-api.md) - Server configuration options
