"""Webhook-specific database entities for JVspatial.

This module provides Entity classes for webhook event tracking, idempotency management,
and response caching using the JVspatial GraphContext system.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from pydantic import Field

from jvspatial.core.entities import Object


class WebhookEvent(Object):
    """Entity for tracking webhook events and their processing status.

    This entity stores webhook event data, processing status, and metadata
    for tracking and debugging webhook processing.
    """

    # Event identification
    idempotency_key: Optional[str] = Field(
        None, description="Unique idempotency key for the event"
    )
    webhook_route: Optional[str] = Field(None, description="Webhook route identifier")
    event_type: Optional[str] = Field(None, description="Type of webhook event")
    source: Optional[str] = Field(None, description="Source system/service")

    # Request data
    http_method: str = Field("POST", description="HTTP method used")
    request_path: str = Field(..., description="Request URL path")
    request_headers: Dict[str, str] = Field(
        default_factory=dict, description="Request headers"
    )
    content_type: str = Field("application/json", description="Content type of payload")
    raw_payload: bytes = Field(b"", description="Raw request payload")
    parsed_payload: Optional[Dict[str, Any]] = Field(
        None, description="Parsed payload data"
    )
    payload_size: int = Field(0, description="Size of payload in bytes")

    # Processing status
    status: str = Field(
        "received",
        description="Processing status (received, processing, processed, failed)",
    )
    processing_started_at: Optional[datetime] = Field(
        None, description="When processing started"
    )
    processing_completed_at: Optional[datetime] = Field(
        None, description="When processing completed"
    )
    processing_duration_ms: Optional[int] = Field(
        None, description="Processing duration in milliseconds"
    )

    # Authentication and security
    hmac_verified: bool = Field(
        False, description="Whether HMAC signature was verified"
    )
    user_id: Optional[str] = Field(None, description="ID of authenticated user")
    api_key_id: Optional[str] = Field(None, description="ID of API key used")

    # Response data
    response_data: Optional[Dict[str, Any]] = Field(
        None, description="Response data returned"
    )
    response_status_code: int = Field(200, description="HTTP response status code")

    # Error information
    error_message: Optional[str] = Field(
        None, description="Error message if processing failed"
    )
    error_details: Optional[Dict[str, Any]] = Field(
        None, description="Detailed error information"
    )
    retry_count: int = Field(0, description="Number of retry attempts")

    # Async processing
    task_id: Optional[str] = Field(None, description="Task ID for async processing")
    is_async: bool = Field(False, description="Whether processed asynchronously")

    # Metadata
    webhook_config: Dict[str, Any] = Field(
        default_factory=dict, description="Endpoint configuration"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When event was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="When event was last updated"
    )
    expires_at: Optional[datetime] = Field(
        None, description="When event expires (for cleanup)"
    )

    class Meta:
        """Entity metadata configuration."""

        indexes = [
            "idempotency_key",
            "webhook_route",
            "status",
            "created_at",
            "expires_at",
            "user_id",
            "api_key_id",
        ]


class WebhookIdempotencyKey(Object):
    """Entity for managing webhook idempotency keys and response caching.

    This entity provides fast lookup for duplicate webhook requests and
    cached responses to ensure idempotent webhook processing.
    """

    # Idempotency key management
    idempotency_key: str = Field(..., description="Unique idempotency key")
    webhook_route: Optional[str] = Field(None, description="Webhook route identifier")
    webhook_event_id: Optional[str] = Field(
        None, description="ID of related WebhookEvent"
    )

    # Request fingerprint
    request_hash: str = Field(..., description="Hash of request payload and headers")
    http_method: str = Field("POST", description="HTTP method")
    request_path: str = Field(..., description="Request URL path")

    # Response caching
    cached_response: Dict[str, Any] = Field(
        default_factory=dict, description="Cached response data"
    )
    response_status_code: int = Field(200, description="Cached response status code")

    # Status tracking
    is_processed: bool = Field(False, description="Whether request has been processed")
    processing_status: str = Field("pending", description="Current processing status")

    # Timestamps
    first_seen_at: datetime = Field(
        default_factory=datetime.utcnow, description="When first seen"
    )
    last_accessed_at: datetime = Field(
        default_factory=datetime.utcnow, description="When last accessed"
    )
    expires_at: datetime = Field(..., description="When key expires")

    class Meta:
        """Entity metadata configuration."""

        indexes = [
            "idempotency_key",
            "webhook_route",
            "request_hash",
            "expires_at",
            "is_processed",
        ]


class WebhookRetryRecord(Object):
    """Entity for tracking webhook retry attempts and exponential backoff.

    This entity manages retry logic for failed webhook processing,
    including exponential backoff timing and failure tracking.
    """

    # Retry identification
    webhook_event_id: str = Field(..., description="ID of related WebhookEvent")
    retry_attempt: int = Field(1, description="Current retry attempt number")

    # Retry scheduling
    next_retry_at: datetime = Field(..., description="When to attempt next retry")
    max_retries: int = Field(5, description="Maximum number of retries")
    backoff_multiplier: float = Field(2.0, description="Exponential backoff multiplier")
    base_delay_seconds: int = Field(
        60, description="Base delay between retries in seconds"
    )

    # Failure tracking
    last_error: Optional[str] = Field(None, description="Last error message")
    error_count: int = Field(0, description="Total number of errors")
    consecutive_failures: int = Field(0, description="Consecutive failure count")

    # Status
    is_exhausted: bool = Field(
        False, description="Whether all retries have been exhausted"
    )
    is_paused: bool = Field(False, description="Whether retries are paused")

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="When last updated"
    )

    class Meta:
        """Entity metadata configuration."""

        indexes = [
            "webhook_event_id",
            "next_retry_at",
            "is_exhausted",
            "is_paused",
        ]


# Utility functions for webhook entity management


async def create_webhook_event(
    idempotency_key: Optional[str] = None,
    webhook_route: Optional[str] = None,
    request_path: str = "/webhook/unknown",
    raw_payload: bytes = b"",
    content_type: str = "application/json",
    parsed_payload: Optional[Dict[str, Any]] = None,
    hmac_verified: bool = False,
    user_id: Optional[str] = None,
    webhook_config: Optional[Dict[str, Any]] = None,
    ttl_hours: int = 24,
) -> WebhookEvent:
    """Create a new webhook event record.

    Args:
        idempotency_key: Unique idempotency key
        webhook_route: Webhook route identifier
        request_path: Request URL path
        raw_payload: Raw request payload
        content_type: Content type of payload
        parsed_payload: Parsed payload data
        hmac_verified: Whether HMAC was verified
        user_id: ID of authenticated user
        webhook_config: Endpoint configuration
        ttl_hours: Hours until event expires

    Returns:
        Created WebhookEvent entity
    """
    expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

    # Create event with concrete status code defaults for typing
    event = WebhookEvent(
        idempotency_key=idempotency_key,
        webhook_route=webhook_route,
        request_path=request_path,
        raw_payload=raw_payload,
        content_type=content_type,
        parsed_payload=parsed_payload,
        payload_size=len(raw_payload),
        hmac_verified=hmac_verified,
        user_id=user_id,
        webhook_config=webhook_config or {},
        expires_at=expires_at,
        event_type="webhook",
        source="external",
        http_method="POST",
        status="pending",
        processing_started_at=datetime.utcnow(),
        processing_completed_at=None,
        processing_duration_ms=0,
        api_key_id=None,
        response_data=None,
        response_status_code=200,
        error_message=None,
        error_details=None,
        retry_count=0,
        task_id=None,
        is_async=False,
    )

    await event.save()
    return event


async def get_or_create_idempotency_key(
    idempotency_key: str,
    webhook_route: Optional[str] = None,
    request_path: str = "/webhook/unknown",
    request_hash: str = "",
    ttl_hours: int = 24,
) -> Tuple[WebhookIdempotencyKey, bool]:
    """Get existing or create new idempotency key record.

    Args:
        idempotency_key: Unique idempotency key
        webhook_route: Webhook route identifier
        request_path: Request URL path
        request_hash: Hash of request payload and headers
        ttl_hours: Hours until key expires

    Returns:
        Tuple of (WebhookIdempotencyKey, is_new_record)
    """
    # Try to find existing key
    existing_keys = await WebhookIdempotencyKey.find(
        {"idempotency_key": idempotency_key}
    )
    existing = existing_keys[0] if existing_keys else None

    if existing:
        # Update last accessed time
        existing.last_accessed_at = datetime.utcnow()
        await existing.save()
        return existing, False

    # Create new key
    expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

    key_record = WebhookIdempotencyKey(
        idempotency_key=idempotency_key,
        webhook_route=webhook_route,
        request_hash=request_hash,
        request_path=request_path,
        expires_at=expires_at,
        webhook_event_id=None,
        http_method="POST",
        response_status_code=200,
        is_processed=False,
        processing_status="pending",
    )

    await key_record.save()
    from typing import cast as _cast

    return _cast(WebhookIdempotencyKey, key_record), True


async def mark_idempotency_key_processed(
    idempotency_key: str,
    response_data: Dict[str, Any],
    status_code: int = 200,
    webhook_event_id: Optional[str] = None,
) -> Optional[WebhookIdempotencyKey]:
    """Mark idempotency key as processed and cache response.

    Args:
        idempotency_key: Unique idempotency key
        response_data: Response data to cache
        status_code: HTTP status code
        webhook_event_id: ID of related webhook event

    Returns:
        Updated WebhookIdempotencyKey or None if not found
    """
    key_records = await WebhookIdempotencyKey.find({"idempotency_key": idempotency_key})
    key_record = key_records[0] if key_records else None

    if not key_record:
        return None

    # Ensure we have a valid key record
    if key_record is None:
        raise ValueError("Key record not found")

    # Update record with response data
    key_record.is_processed = True
    key_record.processing_status = "completed"
    key_record.cached_response = response_data
    key_record.response_status_code = status_code
    key_record.webhook_event_id = webhook_event_id
    key_record.last_accessed_at = datetime.utcnow()

    await key_record.save()
    return key_record


async def cleanup_expired_webhook_data() -> Dict[str, int]:
    """Clean up expired webhook events and idempotency keys.

    Returns:
        Dictionary with counts of cleaned up records
    """
    now = datetime.utcnow()

    # Clean up expired webhook events
    expired_events = await WebhookEvent.find({"expires_at": {"$lt": now}})

    for _event_count, event in enumerate(expired_events, 1):
        await event.delete()

    # Clean up expired idempotency keys
    expired_keys = await WebhookIdempotencyKey.find({"expires_at": {"$lt": now}})

    for _key_count, key in enumerate(expired_keys, 1):
        await key.delete()

    # Clean up exhausted retry records older than 7 days
    week_ago = now - timedelta(days=7)
    old_retries = await WebhookRetryRecord.find(
        {"is_exhausted": True, "updated_at": {"$lt": week_ago}}
    )

    for _retry_count, retry in enumerate(old_retries, 1):
        await retry.delete()

    return {
        "events_cleaned": len(expired_events),
        "keys_cleaned": len(expired_keys),
        "retries_cleaned": len(old_retries),
    }


# Export main classes and functions
__all__ = [
    "WebhookEvent",
    "WebhookIdempotencyKey",
    "WebhookRetryRecord",
    "create_webhook_event",
    "get_or_create_idempotency_key",
    "mark_idempotency_key_processed",
    "cleanup_expired_webhook_data",
]
