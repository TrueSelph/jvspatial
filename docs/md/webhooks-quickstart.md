# JVspatial Webhooks Quickstart

JVspatial provides powerful webhook functionality through the `@webhook_endpoint` decorator, enabling secure, reliable webhook processing with features like HMAC verification, idempotency handling, and asynchronous processing.

## Simplified Response Handling

Webhook endpoints use the standard endpoint response methods (`endpoint.success()`, `endpoint.bad_request()`, `endpoint.server_error()`, etc.) instead of webhook-specific response functions. This provides consistency across all endpoint types while maintaining proper HTTP status codes and response formatting.

## Basic Usage

### Simple Webhook Endpoint

```python
from jvspatial.api.webhook.decorators import webhook_endpoint

@webhook_endpoint("/webhook/simple")
async def simple_webhook(payload: dict, endpoint):
    """Process webhook payload and return response."""
    event_type = payload.get("type", "unknown")

    # Process the event
    print(f"Received webhook: {event_type}")

    # Return standardized response
    return endpoint.success(
        message=f"Successfully processed {event_type} event",
        data={"status": "processed"}
    )
```

### Walker-Based Webhook

```python
from jvspatial.api.webhook.decorators import webhook_endpoint
from jvspatial.core.entities import Walker, Node, on_visit

@webhook_endpoint("/webhook/data-update")
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
    "/webhook/payment",
    hmac_secret="your-webhook-secret"
)
async def payment_webhook(payload: dict, endpoint):
    # HMAC signature is automatically verified by middleware
    # Only authenticated requests reach this handler

    payment_id = payload.get("payment_id")
    return endpoint.success(
        message="Payment processed",
        data={"status": "processed", "payment_id": payment_id}
    )
```

### Path-Based Authentication

```python
@webhook_endpoint(
    "/webhook/stripe/{key}",
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

    return endpoint.success(
        message="Webhook received",
        data={"status": "received"}
    )
```

## Advanced Features

### Idempotency Handling

```python
@webhook_endpoint(
    "/webhook/order",
    hmac_secret="order-secret",
    idempotency_ttl_hours=48  # Keep idempotency records for 2 days
)
async def order_webhook(payload: dict, endpoint):
    """Webhook with idempotency protection against duplicate requests."""
    # Duplicate requests (same idempotency key) return cached response

    order_id = payload.get("order_id")
    # Process order...

    return endpoint.success(
        message="Order processed",
        data={"status": "processed", "order_id": order_id}
    )
```

### Asynchronous Processing

```python
@webhook_endpoint(
    "/webhook/bulk-process",
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
    return endpoint.success(
        message="Batch processing initiated",
        data={
            "status": "processed",
            "batch_id": batch_id,
            "record_count": len(records)
        }
    )
```

### Permission-Based Access Control

```python
@webhook_endpoint(
    "/webhook/admin",
    permissions=["admin_webhooks"],
    roles=["admin", "webhook_manager"]
)
async def admin_webhook(payload: dict, endpoint):
    """Webhook requiring specific permissions and roles."""
    # Only users with admin_webhooks permission AND
    # admin or webhook_manager role can access this

    return endpoint.success(
        message="Admin webhook processed",
        data={"status": "processed"}
    )
```

## Payload Processing

### Automatic Payload Injection

The webhook decorators automatically inject the appropriate payload format based on your function parameters:

```python
@webhook_endpoint("/webhook/flexible")
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
        return endpoint.success(
            message="JSON payload processed",
            data=payload
        )
    else:
        # Process raw body for other content types
        return endpoint.success(
            message="Raw payload received",
            data={
                "status": "received",
                "content_type": content_type,
                "size": len(raw_body)
            }
        )
```

## Error Handling

```python
@webhook_endpoint("/webhook/robust")
async def robust_webhook(payload: dict, endpoint):
    """Webhook with comprehensive error handling."""

    try:
        # Validate required fields
        if "required_field" not in payload:
            return endpoint.bad_request(
                message="Missing required_field"
            )

        # Process payload...
        result = process_data(payload)

        return endpoint.success(
            message="Webhook processed successfully",
            data={"status": "processed", "result": result}
        )

    except ValueError as e:
        return endpoint.bad_request(
            message=f"Validation error: {e}"
        )
    except Exception as e:
        return endpoint.server_error(
            message="Internal processing error"
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
        "/webhook/simple",
        json={"type": "test_event", "data": {"test": True}},
        headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"

    # Test with idempotency key
    response = client.post(
        "/webhook/simple",
        json={"type": "test_event"},
        headers={
            "Content-Type": "application/json",
            "X-Idempotency-Key": "test-key-123"
        }
    )

    assert response.status_code == 200

    # Duplicate request should return cached response
    response2 = client.post(
        "/webhook/simple",
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

## Response Methods

Webhook endpoints use standard endpoint response methods, providing consistency across all endpoint types.

# Standard endpoint response methods
@webhook_endpoint("/webhook/new")
async def new_webhook(payload: dict, endpoint):
    # Success response
    return endpoint.success(
        message="Event processed",
        data={"status": "processed"}
    )

    # Error response
    return endpoint.bad_request(
        message="Validation failed"
    )
```

## Authenticated Webhooks



```python


@webhook_endpoint(
    "/webhook/modern/{key}",
    path_key_auth=True,
    hmac_secret="webhook-secret"
)
async def modern_webhook(payload: dict, endpoint):
    # Automatic payload injection and response helpers
    return endpoint.success(
        message="Webhook processed",
        data={"status": "processed"}
    )
```

