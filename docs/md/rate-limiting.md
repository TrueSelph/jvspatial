# Rate Limiting

jvspatial provides comprehensive rate limiting to protect your API from abuse and ensure fair resource usage. Rate limits can be configured globally, per-endpoint, or per-API key.

## Overview

Rate limiting controls how many requests a client can make within a specific time window. When a limit is exceeded, the API returns a `429 Too Many Requests` response.

## Features

- **Per-Endpoint Configuration**: Different limits for different endpoints
- **In-Memory Storage**: Fast, efficient counter storage
- **Client Identification**: Tracks by IP address or authenticated user/API key
- **Configurable Windows**: Flexible time windows (seconds, minutes, etc.)
- **Clear Error Responses**: Includes retry information in headers

## Configuration

### Enable Rate Limiting

```python
from jvspatial.api import Server

server = Server(
    title="My API",
    rate_limit_enabled=True,  # Enable rate limiting
    rate_limit_default_requests=60,  # Default: 60 requests
    rate_limit_default_window=60,  # Default: 60 seconds (1 minute)
    db_type="json"
)
```

### Per-Endpoint Rate Limits

Configure rate limits for specific endpoints using the `@endpoint` decorator:

```python
from jvspatial.api import endpoint
from jvspatial.core import Walker, on_visit
from jvspatial.core.entities import Node

# Expensive operation: 10 requests per minute
@endpoint("/api/expensive", methods=["POST"], rate_limit={"requests": 10, "window": 60})
class ExpensiveOperation(Walker):
    @on_visit(Node)
    async def process(self, here: Node):
        # Heavy computation
        self.response = {"result": "processed"}

# Bulk operation: 5 requests per 5 minutes
@endpoint("/api/bulk", methods=["POST"], rate_limit={"requests": 5, "window": 300})
class BulkProcessor(Walker):
    @on_visit(Node)
    async def process(self, here: Node):
        # Bulk processing
        self.response = {"status": "completed"}
```

### Server Configuration Overrides

Override rate limits via server configuration:

```python
server = Server(
    title="My API",
    rate_limit_enabled=True,
    rate_limit_default_requests=60,
    rate_limit_default_window=60,
    rate_limit_overrides={
        "/api/search": {"requests": 20, "window": 60},
        "/api/export": {"requests": 5, "window": 300},
    },
    db_type="json"
)
```

## How It Works

### Client Identification

Rate limits are tracked per client identifier:

1. **Authenticated Users/API Keys**: If the request is authenticated, the user ID or API key ID is used
2. **IP Address**: For unauthenticated requests, IP address + user agent hash is used

This ensures:
- Different users have separate rate limit counters
- API keys have their own counters (useful for per-key limits)
- IP-based tracking for anonymous requests

### Time Windows

Rate limits use sliding windows:
- Each request is recorded with a timestamp
- Old requests outside the window are automatically cleaned up
- The limit is checked against requests within the current window

Example: With a limit of 60 requests per 60 seconds:
- Request at 10:00:00 - allowed (1/60)
- Request at 10:00:30 - allowed (2/60)
- ...
- Request at 10:00:59 - allowed (60/60)
- Request at 10:01:00 - allowed (oldest request expired, now 59/60)
- Request at 10:01:01 - blocked (60/60, oldest still within window)

## Rate Limit Responses

When a rate limit is exceeded, the API returns:

**Status Code**: `429 Too Many Requests`

**Response Body**:
```json
{
  "error_code": "rate_limit_exceeded",
  "message": "Rate limit exceeded: 60 requests per 60 seconds",
  "limit": 60,
  "window": 60
}
```

**Response Headers**:
```
X-RateLimit-Limit: 60
X-RateLimit-Window: 60
Retry-After: 60
```

## Examples

### Basic Rate Limiting

```python
from jvspatial.api import Server, endpoint

server = Server(
    title="My API",
    rate_limit_enabled=True,
    rate_limit_default_requests=100,  # 100 requests
    rate_limit_default_window=60,  # per minute
    db_type="json"
)

# This endpoint uses the default limit (100 req/min)
@endpoint("/api/data", methods=["GET"])
async def get_data():
    return {"data": "..."}
```

### Custom Per-Endpoint Limits

```python
# High-frequency endpoint: 200 requests per minute
@endpoint("/api/status", methods=["GET"], rate_limit={"requests": 200, "window": 60})
async def get_status():
    return {"status": "ok"}

# Low-frequency endpoint: 10 requests per hour
@endpoint("/api/report", methods=["POST"], rate_limit={"requests": 10, "window": 3600})
async def generate_report():
    return {"report": "..."}
```

### Rate Limiting with Authentication

Rate limits work seamlessly with authentication:

```python
# Authenticated endpoint with custom rate limit
@endpoint(
    "/api/user-data",
    methods=["GET"],
    auth=True,
    rate_limit={"requests": 30, "window": 60}
)
async def get_user_data():
    return {"user": "data"}
```

Each authenticated user has their own rate limit counter, so User A's requests don't count against User B's limit.

### Rate Limiting with API Keys

API keys can have custom rate limits:

```python
# Create API key with custom rate limit
import requests

response = requests.post(
    "http://localhost:8000/auth/api-keys",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "name": "High-Volume Key",
        "rate_limit_override": 1000  # 1000 requests per minute
    }
)
```

The API key's `rate_limit_override` takes precedence over endpoint-specific limits.

## Best Practices

1. **Set Reasonable Defaults**: Start with conservative limits (e.g., 60 req/min)
2. **Adjust Per Endpoint**: Use higher limits for lightweight endpoints, lower for expensive ones
3. **Consider User Tiers**: Use API key rate limit overrides for premium users
4. **Monitor Usage**: Track rate limit hits to identify bottlenecks
5. **Provide Clear Errors**: The `Retry-After` header helps clients implement backoff
6. **Test Limits**: Verify rate limiting works as expected in your environment

## Client Implementation

### Handling Rate Limit Responses

Clients should implement exponential backoff when receiving 429 responses:

```python
import time
import requests

def make_request_with_retry(url, headers, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)

        if response.status_code == 429:
            # Get retry delay from header
            retry_after = int(response.headers.get("Retry-After", 60))

            # Exponential backoff
            wait_time = retry_after * (2 ** attempt)

            if attempt < max_retries - 1:
                time.sleep(wait_time)
                continue
            else:
                raise Exception("Rate limit exceeded after retries")

        return response
```

### Checking Rate Limit Status

While jvspatial doesn't provide a rate limit status endpoint, clients can:
- Monitor 429 responses
- Track request frequency
- Implement client-side throttling

## Advanced Configuration

### Disabling Rate Limiting for Specific Endpoints

To disable rate limiting for an endpoint, set a very high limit:

```python
@endpoint(
    "/api/internal",
    methods=["GET"],
    rate_limit={"requests": 999999, "window": 1}
)
async def internal_endpoint():
    return {"internal": "data"}
```

Or exclude the endpoint from rate limiting by not configuring it (it will use default if enabled).

### Per-User Rate Limits

Rate limits are automatically per-user when using authentication:
- Each authenticated user has separate counters
- API keys have separate counters
- Unauthenticated requests are tracked by IP

## Troubleshooting

### Rate Limits Not Working

1. Verify `rate_limit_enabled=True` in server configuration
2. Check middleware is registered (should see log message on startup)
3. Ensure endpoint has rate limit configuration
4. Check that requests are being tracked (verify client identification)

### Too Many False Positives

- Increase default limits
- Adjust per-endpoint limits based on actual usage
- Consider using API key rate limit overrides for trusted clients

### Rate Limits Too Permissive

- Decrease default limits
- Add stricter per-endpoint limits
- Monitor for abuse patterns

## Performance Considerations

- **In-Memory Storage**: Rate limit counters are stored in memory for speed
- **Automatic Cleanup**: Old entries are cleaned up automatically
- **Minimal Overhead**: Rate limiting adds minimal latency (<1ms per request)
- **Scalability**: For distributed systems, consider Redis-based rate limiting (future enhancement)

## See Also

- [API Keys Guide](api-keys.md) - API key authentication with rate limits
- [Authentication Guide](authentication.md) - General authentication
- [REST API Guide](rest-api.md) - API endpoint documentation
