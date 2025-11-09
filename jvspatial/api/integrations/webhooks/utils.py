"""Webhook utility functions for JVspatial.

This module provides helper functions for webhook processing including:
- HMAC signature verification
- Idempotency key management
- Payload validation
- Request preprocessing
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, Request


class WebhookConfig:
    """Configuration class for webhook processing."""

    def __init__(
        self,
        hmac_secret: Optional[str] = None,
        hmac_algorithm: str = "sha256",
        max_payload_size: int = 1024 * 1024,  # 1MB default
        idempotency_ttl: int = 3600,  # 1 hour default
        https_required: bool = True,
        allowed_content_types: Optional[List[str]] = None,
    ):
        self.hmac_secret = hmac_secret
        self.hmac_algorithm = hmac_algorithm
        self.max_payload_size = max_payload_size
        self.idempotency_ttl = idempotency_ttl
        self.https_required = https_required
        self.allowed_content_types = allowed_content_types or [
            "application/json",
            "application/x-www-form-urlencoded",
            "application/xml",
            "text/plain",
            "text/xml",
        ]


class IdempotencyManager:
    """Simple in-memory idempotency key manager.

    In production, this should be replaced with Redis or similar persistent storage.
    """

    def __init__(self, ttl_seconds: int = 3600):
        self._cache: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}
        self.ttl_seconds = ttl_seconds

    def is_duplicate(
        self, idempotency_key: str
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Check if idempotency key has been seen before.

        Args:
            idempotency_key: The idempotency key to check

        Returns:
            Tuple of (is_duplicate, cached_response_if_duplicate)
        """
        if not idempotency_key:
            return False, None

        # Clean expired entries
        self._cleanup_expired()

        if idempotency_key in self._cache:
            _, cached_response = self._cache[idempotency_key]
            return True, cached_response

        return False, None

    def store_response(self, idempotency_key: str, response: Dict[str, Any]) -> None:
        """Store a response for future duplicate detection.

        Args:
            idempotency_key: The idempotency key
            response: The response to cache
        """
        if not idempotency_key:
            return

        expiry = datetime.now() + timedelta(seconds=self.ttl_seconds)
        self._cache[idempotency_key] = (expiry, response)

        # Periodic cleanup
        if len(self._cache) > 1000:  # Prevent unbounded growth
            self._cleanup_expired()

    def _cleanup_expired(self) -> None:
        """Remove expired entries from cache."""
        now = datetime.now()
        expired_keys = [key for key, (expiry, _) in self._cache.items() if expiry < now]
        for key in expired_keys:
            del self._cache[key]


# Global idempotency manager instance
_idempotency_manager = IdempotencyManager()


def generate_hmac_signature(
    payload: bytes, secret: str, algorithm: str = "sha256", prefix: str = "sha256="
) -> str:
    """Generate HMAC signature for webhook payload.

    Args:
        payload: Raw payload bytes
        secret: HMAC secret key
        algorithm: Hash algorithm (default: sha256)
        prefix: Signature prefix (default: sha256=)

    Returns:
        HMAC signature string

    Example:
        >>> payload = b'{"test": "data"}'
        >>> secret = "my-secret-key"  # pragma: allowlist secret
        >>> sig = generate_hmac_signature(payload, secret)
        >>> print(sig)  # sha256=abc123...
    """
    if algorithm not in hashlib.algorithms_available:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")

    mac = hmac.new(secret.encode("utf-8"), payload, getattr(hashlib, algorithm))

    return f"{prefix}{mac.hexdigest()}"


def verify_hmac_signature(
    payload: bytes,
    signature: str,
    secret: str,
    algorithm: str = "sha256",
    prefix: str = "sha256=",
) -> bool:
    """Verify HMAC signature for webhook payload.

    Args:
        payload: Raw payload bytes
        signature: Received signature to verify
        secret: HMAC secret key
        algorithm: Hash algorithm (default: sha256)
        prefix: Expected signature prefix (default: sha256=)

    Returns:
        True if signature is valid, False otherwise

    Example:
        >>> payload = b'{"test": "data"}'
        >>> signature = "sha256=abc123..."
        >>> secret = "my-secret-key"  # pragma: allowlist secret
        >>> is_valid = verify_hmac_signature(payload, signature, secret)
        >>> print(is_valid)  # True or False
    """
    if not signature or not secret:
        return False

    # Remove prefix if present
    if signature.startswith(prefix):
        signature = signature[len(prefix) :]

    try:
        expected_signature = generate_hmac_signature(
            payload, secret, algorithm, ""
        )  # No prefix for comparison

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(signature, expected_signature[len(prefix) :])

    except Exception:
        return False


def extract_idempotency_key(request: Request) -> Optional[str]:
    """Extract idempotency key from request headers.

    Checks multiple common header names:
    - Idempotency-Key
    - X-Idempotency-Key
    - X-Idempotent-Key
    - Idempotent-Key

    Args:
        request: FastAPI request object

    Returns:
        Idempotency key if found, None otherwise
    """
    headers_to_check = [
        "idempotency-key",
        "x-idempotency-key",
        "x-idempotent-key",
        "idempotent-key",
    ]

    for header_name in headers_to_check:
        value = request.headers.get(header_name)
        if value:
            return str(value).strip()

    return None


def extract_hmac_signature(request: Request) -> Optional[str]:
    """Extract HMAC signature from request headers.

    Checks multiple common header names:
    - X-Signature
    - X-Hub-Signature
    - X-Hub-Signature-256
    - Authorization (Bearer format)

    Args:
        request: FastAPI request object

    Returns:
        HMAC signature if found, None otherwise
    """
    headers_to_check = [
        "x-signature",
        "x-hub-signature",
        "x-hub-signature-256",
        "signature",
    ]

    for header_name in headers_to_check:
        value = request.headers.get(header_name)
        if value:
            return str(value).strip()

    # Check Authorization header for Bearer format
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return str(auth_header)[7:].strip()

    return None


def validate_webhook_request(
    request: Request, config: WebhookConfig
) -> Tuple[bool, Optional[str]]:
    """Validate webhook request against configuration.

    Args:
        request: FastAPI request object
        config: Webhook configuration

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check HTTPS requirement
    if config.https_required:
        scheme = request.url.scheme
        if scheme != "https":
            return False, "HTTPS required for webhook endpoints"

    # Check content type
    content_type = request.headers.get("content-type", "").split(";")[0].lower()
    if content_type not in config.allowed_content_types:
        return False, f"Unsupported content type: {content_type}"

    # Check content length if available
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            length = int(content_length)
            if length > config.max_payload_size:
                return False, f"Payload too large: {length} > {config.max_payload_size}"
        except ValueError:
            return False, "Invalid content-length header"

    return True, None


async def process_webhook_payload(request: Request) -> Tuple[bytes, str]:
    """Process and extract webhook payload from request.

    Args:
        request: FastAPI request object

    Returns:
        Tuple of (raw_payload_bytes, content_type)

    Raises:
        HTTPException: If payload cannot be processed
    """
    try:
        # Read raw body
        raw_body = request.body()
        content_type = (
            request.headers.get("content-type", "application/json")
            .split(";")[0]
            .lower()
        )

        return raw_body, content_type

    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to read request payload: {str(e)}"
        )


def parse_webhook_payload(raw_body: bytes, content_type: str) -> Any:
    """Parse webhook payload based on content type.

    Args:
        raw_body: Raw payload bytes
        content_type: Content type header value

    Returns:
        Parsed payload data

    Raises:
        ValueError: If payload cannot be parsed
    """
    if not raw_body:
        return None

    try:
        if content_type == "application/json":
            return json.loads(raw_body.decode("utf-8"))
        elif content_type == "application/x-www-form-urlencoded":
            from urllib.parse import parse_qs

            return parse_qs(raw_body.decode("utf-8"))
        elif content_type in ["application/xml", "text/xml", "text/plain"]:
            # Return raw string for XML/plain text - parsing would require additional dependencies
            return raw_body.decode("utf-8")
        else:
            # Return raw bytes for unknown content types
            return raw_body

    except Exception as e:
        raise ValueError(f"Failed to parse {content_type} payload: {str(e)}")


async def check_idempotency(
    idempotency_key: Optional[str],
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Check if request is a duplicate based on idempotency key.

    Args:
        idempotency_key: The idempotency key from request

    Returns:
        Tuple of (is_duplicate, cached_response_if_duplicate)
    """
    if not idempotency_key:
        return False, None

    try:
        from .models import WebhookIdempotencyKey

        # Look for existing idempotency key
        existing_keys = await WebhookIdempotencyKey.find(
            {
                "idempotency_key": idempotency_key,
                "is_processed": True,
            }
        )
        existing = existing_keys[0] if existing_keys else None

        if existing:
            # Treat as concrete type for type checker
            from typing import cast as _cast

            existing = _cast(WebhookIdempotencyKey, existing)
            # Update last accessed time
            existing.last_accessed_at = datetime.now()
            await existing.save()
            return True, _cast(Dict[str, Any], existing.cached_response)

        return False, None

    except Exception:
        # Fall back to in-memory manager if database is not available
        return _idempotency_manager.is_duplicate(idempotency_key)


async def store_idempotent_response(
    idempotency_key: Optional[str],
    response: Dict[str, Any],
    webhook_event_id: Optional[str] = None,
) -> None:
    """Store response for idempotency checking.

    Args:
        idempotency_key: The idempotency key
        response: Response to store
        webhook_event_id: ID of related webhook event
    """
    if not idempotency_key:
        return

    try:
        from .models import mark_idempotency_key_processed

        # Store in database
        await mark_idempotency_key_processed(
            idempotency_key=idempotency_key,
            response_data=response,
            webhook_event_id=webhook_event_id,
        )

    except Exception:
        # Fall back to in-memory manager if database is not available
        _idempotency_manager.store_response(idempotency_key, response)


def get_webhook_config_from_env() -> WebhookConfig:
    """Create WebhookConfig from environment variables.

    Environment variables:
    - JVSPATIAL_WEBHOOK_HMAC_SECRET: HMAC secret key
    - JVSPATIAL_WEBHOOK_HMAC_ALGORITHM: Hash algorithm (default: sha256)
    - JVSPATIAL_WEBHOOK_MAX_PAYLOAD_SIZE: Maximum payload size in bytes
    - JVSPATIAL_WEBHOOK_IDEMPOTENCY_TTL: Idempotency cache TTL in seconds
    - JVSPATIAL_WEBHOOK_HTTPS_REQUIRED: Require HTTPS (true/false)

    Returns:
        WebhookConfig instance
    """
    import os

    return WebhookConfig(
        hmac_secret=os.getenv("JVSPATIAL_WEBHOOK_HMAC_SECRET"),
        hmac_algorithm=os.getenv("JVSPATIAL_WEBHOOK_HMAC_ALGORITHM", "sha256"),
        max_payload_size=int(
            os.getenv("JVSPATIAL_WEBHOOK_MAX_PAYLOAD_SIZE", "1048576")
        ),  # 1MB
        idempotency_ttl=int(
            os.getenv("JVSPATIAL_WEBHOOK_IDEMPOTENCY_TTL", "3600")
        ),  # 1 hour
        https_required=os.getenv("JVSPATIAL_WEBHOOK_HTTPS_REQUIRED", "true").lower()
        == "true",
    )


# Convenience function for common webhook validation workflow
async def validate_and_process_webhook(
    request: Request, config: Optional[WebhookConfig] = None
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Complete webhook validation and processing workflow.

    Args:
        request: FastAPI request object
        config: Webhook configuration (uses env defaults if None)

    Returns:
        Tuple of (processed_data_dict, cached_response_if_duplicate)

    Raises:
        HTTPException: If validation fails
    """
    if config is None:
        config = get_webhook_config_from_env()

    # Validate request
    is_valid, error_msg = validate_webhook_request(request, config)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Process payload
    raw_body, content_type = await process_webhook_payload(request)

    # Verify HMAC if configured
    if config.hmac_secret:
        signature = extract_hmac_signature(request)
        if not signature:
            raise HTTPException(status_code=400, detail="Missing HMAC signature")

        if not verify_hmac_signature(raw_body, signature, config.hmac_secret):
            raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    # Check idempotency
    idempotency_key = extract_idempotency_key(request)
    is_duplicate, cached_response = await check_idempotency(idempotency_key)

    if is_duplicate:
        return {
            "raw_body": raw_body,
            "content_type": content_type,
            "idempotency_key": idempotency_key,
            "is_duplicate": True,
        }, cached_response

    # Parse payload
    try:
        parsed_payload = parse_webhook_payload(raw_body, content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "raw_body": raw_body,
        "content_type": content_type,
        "parsed_payload": parsed_payload,
        "idempotency_key": idempotency_key,
        "is_duplicate": False,
        "hmac_verified": bool(config.hmac_secret),
    }, None
