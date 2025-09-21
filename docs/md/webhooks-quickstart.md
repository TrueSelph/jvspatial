# JVspatial Webhooks Quickstart

JVspatial provides powerful webhook functionality through the `@webhook_endpoint` and `@webhook_walker_endpoint` decorators, enabling secure, reliable webhook processing with features like HMAC verification, idempotency handling, and asynchronous processing.

## Basic Usage

### Simple Webhook Endpoint

```python
from jvspatial.api.auth.decorators import webhook_endpoint

@webhook_endpoint("/webhooks/simple")
async def simple_webhook(payload: dict, endpoint):
    """Process webhook payload and return response."""
    event_type = payload.get("type", "unknown")

    # Process the event
    print(f"Received webhook: {event_type}")

    # Return standardized webhook response
    return endpoint.webhook_response(
        status="processed",
        message=f"Successfully processed {event_type} event"
    )
```

### Walker-Based Webhook

```python
from jvspatial.api.auth.decorators import webhook_walker_endpoint
from jvspatial.core.entities import Walker, Node, on_visit

@webhook_walker_endpoint("/webhooks/data-update")
class DataUpdateWalker(Walker):
    """Walker that updates graph data based on webhook events."""

    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload
        self.response = {"updates": []}

    @on_visit(Node)
    async def update_data(self, here: Node):
        # Use self.payload to access webhook data
        updates = self.payload.get("updates", [])

        for update in updates:
            node_id = update.get("id")
            if here.id == node_id:
                here.data = update.get("data")
                await here.save()
                self.response["updates"].append(node_id)
```

## Security Features

### HMAC Signature Verification

```python
@webhook_endpoint(
    "/webhooks/payment",
    hmac_secret="your-webhook-secret"
)
async def payment_webhook(payload: dict, endpoint):
    # HMAC signature is automatically verified by middleware
    # Only authenticated requests reach this handler

    payment_id = payload.get("payment_id")
    return endpoint.webhook_response(
        status="processed",
        payment_id=payment_id
    )
```

### Path-Based Authentication

```python
@webhook_endpoint(
    "/webhooks/stripe/{key}",
    path_key_auth=True,
    hmac_secret="stripe-webhook-secret"
)
async def stripe_webhook(raw_body: bytes, content_type: str, endpoint):
    """Webhook with API key embedded in URL path."""
    # API key from path is automatically validated
    # Access raw payload for custom processing

    if content_type == "application/json":
        import json
        payload = json.loads(raw_body.decode('utf-8'))

    return endpoint.webhook_response(status="received")
```

## Advanced Features

### Idempotency Handling

```python
@webhook_endpoint(
    "/webhooks/order",
    hmac_secret="order-secret",
    idempotency_ttl_hours=48  # Keep idempotency records for 2 days
)
async def order_webhook(payload: dict, endpoint):
    """Webhook with idempotency protection against duplicate requests."""
    # Duplicate requests (same idempotency key) return cached response

    order_id = payload.get("order_id")
    # Process order...

    return endpoint.webhook_response(
        status="processed",
        order_id=order_id
    )
```

### Asynchronous Processing

```python
@webhook_endpoint(
    "/webhooks/bulk-process",
    async_processing=True,
    permissions=["process_bulk_data"]
)
async def bulk_processing_webhook(payload: dict, endpoint):
    """Webhook that processes data asynchronously."""
    # This returns immediately with HTTP 200
    # Actual processing happens in background

    batch_id = payload.get("batch_id")
    records = payload.get("records", [])

    # Process large batch of records...
    return endpoint.webhook_response(
        status="processed",
        batch_id=batch_id,
        record_count=len(records)
    )
```

### Permission-Based Access Control

```python
@webhook_endpoint(
    "/webhooks/admin",
    permissions=["admin_webhooks"],
    roles=["admin", "webhook_manager"]
)
async def admin_webhook(payload: dict, endpoint):
    """Webhook requiring specific permissions and roles."""
    # Only users with admin_webhooks permission AND
    # admin or webhook_manager role can access this

    return endpoint.webhook_response(status="processed")
```

## Payload Processing

### Automatic Payload Injection

The webhook decorators automatically inject the appropriate payload format based on your function parameters:

```python
@webhook_endpoint("/webhooks/flexible")
async def flexible_webhook(
    payload: dict,          # Parsed JSON payload
    raw_body: bytes,        # Raw request body
    content_type: str,      # Content-Type header
    endpoint,               # Webhook endpoint helper
    webhook_data: dict      # All webhook metadata
):
    """Function receives all available webhook data."""

    # Access different payload formats as needed
    if content_type == "application/json":
        return endpoint.webhook_response(data=payload)
    else:
        # Process raw body for other content types
        return endpoint.webhook_response(
            status="received",
            content_type=content_type,
            size=len(raw_body)
        )
```

## Error Handling

```python
@webhook_endpoint("/webhooks/robust")
async def robust_webhook(payload: dict, endpoint):
    """Webhook with comprehensive error handling."""

    try:
        # Validate required fields
        if "required_field" not in payload:
            return endpoint.webhook_error(
                message="Missing required_field",
                error_code=400
            )

        # Process payload...
        result = process_data(payload)

        return endpoint.webhook_response(
            status="processed",
            result=result
        )

    except ValueError as e:
        return endpoint.webhook_error(
            message=f"Validation error: {e}",
            error_code=400
        )
    except Exception as e:
        return endpoint.webhook_error(
            message="Internal processing error",
            error_code=500
        )
```

## Server Integration

Webhook endpoints are automatically discovered and registered by the server:

```python
from jvspatial.api.server import Server

# Create server - webhook middleware is automatically added
# when webhook endpoints are detected
server = Server(
    title="My Webhook API",
    description="API with webhook functionality"
)

# Webhook endpoints are registered via decorators
# No additional setup needed

if __name__ == "__main__":
    server.run()
```

## Configuration

### Environment Variables

Configure webhook behavior using environment variables:

```bash
# HMAC verification
WEBHOOK_HMAC_SECRET=your-global-hmac-secret

# Payload limits
WEBHOOK_MAX_PAYLOAD_SIZE=5242880  # 5MB

# Idempotency
WEBHOOK_IDEMPOTENCY_TTL=3600      # 1 hour

# Security
WEBHOOK_HTTPS_REQUIRED=true
```

### Programmatic Configuration

```python
from jvspatial.api.webhook.middleware import WebhookConfig, WebhookMiddleware

# Custom webhook configuration
config = WebhookConfig(
    hmac_secret="custom-secret",
    max_payload_size=10 * 1024 * 1024,  # 10MB
    https_required=True,
    idempotency_ttl=7200  # 2 hours
)

# Add to server manually if needed
server.app.add_middleware(WebhookMiddleware, config=config)
```

## Testing Webhooks

Use the provided test utilities for testing webhook endpoints:

```python
import pytest
from fastapi.testclient import TestClient
from jvspatial.api.server import Server

# Create test server
server = Server()
client = TestClient(server.app)

def test_webhook_endpoint():
    """Test webhook endpoint functionality."""

    # Test successful webhook
    response = client.post(
        "/webhooks/simple",
        json={"type": "test_event", "data": {"test": True}},
        headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"

    # Test with idempotency key
    response = client.post(
        "/webhooks/simple",
        json={"type": "test_event"},
        headers={
            "Content-Type": "application/json",
            "X-Idempotency-Key": "test-key-123"
        }
    )

    assert response.status_code == 200

    # Duplicate request should return cached response
    response2 = client.post(
        "/webhooks/simple",
        json={"type": "different_event"},  # Different payload
        headers={
            "Content-Type": "application/json",
            "X-Idempotency-Key": "test-key-123"  # Same key
        }
    )

    assert response2.status_code == 200
    # Should get cached response, not process new payload
```

## Database Integration

Webhook events are automatically stored in the database for tracking and debugging:

```python
from jvspatial.api.webhook.entities import WebhookEvent, WebhookIdempotencyKey

# Query webhook events
events = await WebhookEvent.find(
    WebhookEvent.status == "processed",
    WebhookEvent.created_at > some_date
).to_list()

# Clean up expired data
from jvspatial.api.webhook.entities import cleanup_expired_webhook_data

cleanup_stats = await cleanup_expired_webhook_data()
print(f"Cleaned up {cleanup_stats['events_cleaned']} events")
```

## Best Practices

1. **Always use HMAC verification** for external webhooks to ensure authenticity
2. **Set appropriate idempotency TTL** based on your retry policies
3. **Use async processing** for long-running or resource-intensive operations
4. **Implement proper error handling** and return appropriate HTTP status codes
5. **Validate webhook payloads** thoroughly before processing
6. **Use path-based auth** for webhooks from services that support it
7. **Monitor webhook processing** using the built-in database entities
8. **Set reasonable payload size limits** to prevent abuse
9. **Use permissions and roles** to restrict access to sensitive webhook endpoints
10. **Test webhook endpoints thoroughly** including edge cases and error conditions

## Migration from Legacy Webhooks

If you have existing webhook endpoints using the old `{auth_token}` pattern, you can migrate them:

```python
# Old pattern (still supported)
@webhook_endpoint("/webhooks/legacy/{auth_token}")
async def legacy_webhook(request):
    # Manual request processing
    pass

# New pattern (recommended)
@webhook_endpoint(
    "/webhooks/modern/{key}",
    path_key_auth=True,
    hmac_secret="webhook-secret"
)
async def modern_webhook(payload: dict, endpoint):
    # Automatic payload injection and response helpers
    return endpoint.webhook_response(status="processed")
```

The new pattern provides better security, automatic payload processing, standardized responses, and improved error handling.