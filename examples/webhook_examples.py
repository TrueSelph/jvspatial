"""Example webhook implementations using JVspatial.

This module demonstrates how to use the @webhook_endpoint and @webhook_walker_endpoint
decorators to create webhook endpoints with various configurations.
"""

import json
from typing import Any, Dict

from fastapi import Request

from jvspatial.api.auth.decorators import webhook_endpoint, webhook_walker_endpoint
from jvspatial.api.server import Server
from jvspatial.core.entities import Node, Walker, on_visit


# Example 1: Simple webhook endpoint with JSON payload processing
@webhook_endpoint("/webhooks/simple")
async def simple_webhook(payload: dict, endpoint):
    """Simple webhook that processes JSON payloads.

    This endpoint automatically receives parsed JSON data and provides
    a webhook endpoint helper for creating standardized responses.
    """
    # Process the payload
    event_type = payload.get("type", "unknown")
    data = payload.get("data", {})

    # Log the event
    print(f"Received webhook event: {event_type}")

    # Return success response
    return endpoint.webhook_response(
        status="processed",
        message=f"Successfully processed {event_type} event",
        event_type=event_type,
        processed_items=len(data) if isinstance(data, (list, dict)) else 1,
    )


# Example 2: HMAC-verified webhook with idempotency
@webhook_endpoint(
    "/webhooks/payment",
    hmac_secret="your-payment-webhook-secret",  # pragma: allowlist secret
    idempotency_ttl_hours=48,  # Keep idempotency records for 48 hours
)
async def payment_webhook(payload: dict, endpoint):
    """Payment webhook with HMAC verification and idempotency.

    This webhook verifies HMAC signatures and handles duplicate requests
    using idempotency keys to ensure exactly-once processing.
    """
    # Extract payment information
    payment_id = payload.get("payment_id")
    amount = payload.get("amount", 0)
    currency = payload.get("currency", "USD")
    status = payload.get("status", "unknown")

    if not payment_id:
        return endpoint.webhook_error(
            message="Missing payment_id in payload", error_code=400
        )

    # Process payment update
    print(f"Processing payment {payment_id}: {amount} {currency} - {status}")

    # Simulate payment processing
    if status == "completed":
        # Update payment status in your system
        result = {
            "payment_processed": True,
            "payment_id": payment_id,
            "amount": amount,
            "currency": currency,
        }
    else:
        result = {
            "payment_processed": False,
            "payment_id": payment_id,
            "status": status,
        }

    return endpoint.webhook_response(
        status="processed",
        message=f"Payment {payment_id} processed successfully",
        **result,
    )


# Example 3: Path-based authentication webhook
@webhook_endpoint(
    "/webhooks/stripe/{key}",
    path_key_auth=True,
    hmac_secret="stripe-webhook-secret",  # pragma: allowlist secret
)
async def stripe_webhook(raw_body: bytes, content_type: str, endpoint):
    """Stripe webhook with path-based API key authentication.

    This webhook uses path-based authentication where the API key is embedded
    in the URL path, and also verifies Stripe's webhook signatures.
    """
    # Handle raw payload for Stripe signature verification
    if content_type == "application/json":
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return endpoint.webhook_error(
                message="Invalid JSON payload", error_code=400
            )
    else:
        return endpoint.webhook_error(
            message="Unsupported content type", error_code=400
        )

    # Process Stripe event
    event_type = payload.get("type", "unknown")
    event_id = payload.get("id")

    print(f"Processing Stripe event {event_id}: {event_type}")

    # Handle different event types
    if event_type.startswith("payment_intent."):
        # Handle payment intent events
        payment_intent = payload.get("data", {}).get("object", {})
        return endpoint.webhook_response(
            status="processed",
            message=f"Payment intent {event_type} processed",
            event_id=event_id,
            payment_intent_id=payment_intent.get("id"),
        )

    elif event_type.startswith("customer."):
        # Handle customer events
        customer = payload.get("data", {}).get("object", {})
        return endpoint.webhook_response(
            status="processed",
            message=f"Customer {event_type} processed",
            event_id=event_id,
            customer_id=customer.get("id"),
        )

    else:
        # Unknown event type, but still acknowledge receipt
        return endpoint.webhook_response(
            status="received",
            message=f"Event {event_type} received but not processed",
            event_id=event_id,
        )


# Example 4: Asynchronous webhook processing
@webhook_endpoint(
    "/webhooks/bulk-data", async_processing=True, permissions=["process_bulk_data"]
)
async def bulk_data_webhook(payload: dict, endpoint):
    """Bulk data processing webhook with asynchronous handling.

    This webhook immediately returns a 200 response and processes the data
    asynchronously in the background, useful for large payloads or long-running operations.
    """
    # This function won't actually be called for async processing
    # The middleware handles async queueing and returns immediately
    # The actual processing would happen in a background task

    # Extract bulk data information
    batch_id = payload.get("batch_id")
    records = payload.get("records", [])

    print(f"Processing bulk data batch {batch_id} with {len(records)} records")

    # Process each record (this would be done asynchronously)
    processed_count = 0
    for record in records:
        # Simulate record processing
        record_id = record.get("id")
        if record_id:
            processed_count += 1

    return endpoint.webhook_response(
        status="processed",
        message=f"Processed {processed_count} records in batch {batch_id}",
        batch_id=batch_id,
        processed_count=processed_count,
    )


# Example 5: Walker-based webhook for graph updates
@webhook_walker_endpoint("/webhooks/location-update", roles=["location_manager"])
class LocationUpdateWalker(Walker):
    """Walker that updates location data in the graph based on webhook events.

    This example shows how to use Walker classes for webhook processing
    when you need to perform graph traversal and updates.
    """

    def __init__(self, payload: dict):
        """Initialize walker with webhook payload."""
        super().__init__()
        self.payload = payload
        self.response = {"updated_locations": []}

    @on_visit(Node)
    async def update_location_data(self, here: Node):
        """Update location data for nodes based on webhook payload."""
        # Extract location updates from payload
        locations = self.payload.get("locations", [])

        for location_data in locations:
            location_id = location_data.get("id")
            coordinates = location_data.get("coordinates")

            if not location_id or not coordinates:
                continue

            # Find the location node
            location_node = await here.get_related("location", {"id": location_id})

            if location_node:
                # Update coordinates
                location_node.coordinates = coordinates
                location_node.last_updated = location_data.get("timestamp")
                await location_node.save()

                self.response["updated_locations"].append(
                    {"id": location_id, "coordinates": coordinates, "updated": True}
                )

                print(f"Updated location {location_id} with coordinates {coordinates}")
            else:
                self.response["updated_locations"].append(
                    {"id": location_id, "error": "Location not found"}
                )


# Example 6: Advanced webhook with custom validation and error handling
@webhook_endpoint(
    "/webhooks/inventory",
    hmac_secret="inventory-webhook-secret",  # pragma: allowlist secret
    permissions=["manage_inventory"],
    idempotency_ttl_hours=72,
)
async def inventory_webhook(payload: dict, endpoint, request: Request):
    """Advanced inventory webhook with custom validation and error handling.

    This example shows more sophisticated webhook handling including
    custom validation, error handling, and access to the full request object.
    """
    try:
        # Validate required fields
        required_fields = ["item_id", "quantity", "operation"]
        missing_fields = [field for field in required_fields if field not in payload]

        if missing_fields:
            return endpoint.webhook_error(
                message=f"Missing required fields: {', '.join(missing_fields)}",
                error_code=400,
                missing_fields=missing_fields,
            )

        # Extract inventory data
        item_id = payload["item_id"]
        quantity = payload["quantity"]
        operation = payload["operation"]
        warehouse = payload.get("warehouse", "default")

        # Validate operation type
        valid_operations = ["add", "remove", "set", "adjust"]
        if operation not in valid_operations:
            return endpoint.webhook_error(
                message=f"Invalid operation '{operation}'. Must be one of: {', '.join(valid_operations)}",
                error_code=400,
                valid_operations=valid_operations,
            )

        # Validate quantity
        if not isinstance(quantity, (int, float)) or quantity < 0:
            return endpoint.webhook_error(
                message="Quantity must be a non-negative number", error_code=400
            )

        # Process inventory update
        print(
            f"Processing inventory {operation}: {item_id} quantity {quantity} at {warehouse}"
        )

        # Simulate inventory processing
        current_quantity = 100  # This would come from your inventory system

        if operation == "add":
            new_quantity = current_quantity + quantity
        elif operation == "remove":
            new_quantity = max(0, current_quantity - quantity)
        elif operation == "set":
            new_quantity = quantity
        elif operation == "adjust":
            new_quantity = max(
                0, current_quantity + quantity
            )  # Can be negative for adjustments

        # Return detailed response
        return endpoint.webhook_response(
            status="processed",
            message=f"Inventory {operation} completed for item {item_id}",
            item_id=item_id,
            operation=operation,
            warehouse=warehouse,
            previous_quantity=current_quantity,
            new_quantity=new_quantity,
            quantity_change=new_quantity - current_quantity,
        )

    except Exception as e:
        # Handle unexpected errors
        print(f"Error processing inventory webhook: {e}")
        return endpoint.webhook_error(
            message="Internal processing error",
            error_code=500,
            error_type=type(e).__name__,
        )


# Example server setup with webhook endpoints
if __name__ == "__main__":
    # Create server instance
    server = Server(
        title="Webhook Examples API",
        description="Demonstrates JVspatial webhook functionality",
    )

    # The webhook endpoints are automatically registered via decorators
    # The server will automatically add webhook middleware when it detects webhook endpoints

    print("Webhook endpoints registered:")
    print("- POST /webhooks/simple - Simple JSON webhook")
    print("- POST /webhooks/payment - Payment webhook with HMAC + idempotency")
    print("- POST /webhooks/stripe/{key} - Stripe webhook with path auth")
    print("- POST /webhooks/bulk-data - Async processing webhook")
    print("- POST /webhooks/location-update - Walker-based location updates")
    print("- POST /webhooks/inventory - Advanced inventory webhook")

    # Run the server
    server.run(host="0.0.0.0", port=8000)
