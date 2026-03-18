"""Webhook middleware for JVspatial FastAPI integration.

This middleware handles all webhook-specific processing including:
- HMAC signature verification
- Idempotency key management
- Payload preprocessing and validation
- HTTPS enforcement
- Route parameter extraction
"""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from jvspatial.api.constants import APIRoutes
from jvspatial.config import use_background_processing

from .utils import (
    WebhookConfig,
    extract_idempotency_key,
    get_webhook_config_from_env,
    store_idempotent_response,
    validate_and_process_webhook,
)
from .webhook_auth import authenticate_webhook_api_key

logger = logging.getLogger(__name__)


class WebhookMiddleware(BaseHTTPMiddleware):
    """Middleware for processing webhook requests.

    This middleware handles all webhook-specific processing including authentication,
    HMAC verification, idempotency checking, and payload preprocessing.

    The middleware runs before the endpoint handler and populates request.state with:
    - raw_body: Raw request body bytes
    - content_type: Content type of the request
    - webhook_route: Extracted route parameter (if present)
    - idempotency_key: Idempotency key from headers (if present)
    - is_duplicate_request: Whether this is a duplicate request
    - cached_response: Cached response for duplicate requests
    - hmac_verified: Whether HMAC signature was verified
    - parsed_payload: Parsed payload data (for JSON payloads)
    - webhook_config: Endpoint-specific webhook configuration
    """

    def __init__(
        self,
        app,
        config: Optional[WebhookConfig] = None,
        webhook_path_pattern: str = "/webhook/",
        server=None,
    ):
        """Initialize webhook middleware.

        Args:
            app: FastAPI application
            config: Webhook configuration (uses env defaults if None)
            webhook_path_pattern: Path pattern to identify webhook requests
            server: Server instance for accessing endpoint metadata
        """
        super().__init__(app)
        self.config = config or get_webhook_config_from_env()
        self.webhook_path_pattern = webhook_path_pattern
        self.server = server

        logger.info(
            f"WebhookMiddleware initialized with pattern: {webhook_path_pattern}"
        )
        if self.config.hmac_secret:
            logger.info("HMAC verification enabled")
        else:
            logger.info(
                "HMAC verification disabled - no secret configured "
                "(API key auth still available per endpoint)"
            )

    def _get_endpoint_webhook_config(
        self, request: Request
    ) -> Optional[Dict[str, Any]]:
        """Extract webhook configuration from endpoint metadata.

        Uses cached registry result from dispatch when available.

        Args:
            request: FastAPI request object

        Returns:
            Dictionary with endpoint-specific webhook configuration or None
        """
        if not self.server:
            return None

        # Use cached registry result from dispatch
        endpoints = getattr(request.state, "_webhook_endpoints_match", None)
        if endpoints is None:
            endpoints = (
                self.server._endpoint_registry.get_webhook_endpoints_matching_path(
                    request.url.path, request.method
                )
            )

        if endpoints:
            first_match = endpoints[0]
            return self._extract_webhook_metadata(first_match.handler)

        return None

    def _extract_webhook_metadata(self, endpoint_obj) -> Dict[str, Any]:
        """Extract webhook metadata from endpoint function or walker class.

        Args:
            endpoint_obj: Function or Walker class with webhook metadata

        Returns:
            Dictionary with webhook configuration
        """
        # Get endpoint config - webhook endpoints must use _jvspatial_endpoint_config
        endpoint_config = getattr(endpoint_obj, "_jvspatial_endpoint_config", None)

        if not endpoint_config:
            # No config available - return defaults
            return {
                "hmac_secret": None,
                "signature_required": False,
                "idempotency_key_field": "X-Idempotency-Key",
                "idempotency_ttl_hours": 24,
                "async_processing": False,
                "auth_required": False,
                "required_permissions": [],
                "required_roles": [],
                "webhook_auth": None,
                "api_key_header": "x-api-key",  # pragma: allowlist secret
                "api_key_query_param": "api_key",  # pragma: allowlist secret
            }

        # Extract from endpoint config
        return {
            "hmac_secret": endpoint_config.get("hmac_secret"),
            "signature_required": endpoint_config.get("signature_required", False),
            "idempotency_key_field": endpoint_config.get(
                "idempotency_key_field", "X-Idempotency-Key"
            ),
            "idempotency_ttl_hours": endpoint_config.get("idempotency_ttl_hours", 24),
            "async_processing": endpoint_config.get("async_processing", False),
            "auth_required": endpoint_config.get("auth_required", False),
            "required_permissions": endpoint_config.get("required_permissions", []),
            "required_roles": endpoint_config.get("required_roles", []),
            "webhook_auth": endpoint_config.get("webhook_auth"),
            "api_key_header": endpoint_config.get(
                "api_key_header", "x-api-key"
            ),  # pragma: allowlist secret
            "api_key_query_param": endpoint_config.get(  # pragma: allowlist secret
                "api_key_query_param", "api_key"
            ),
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process webhook requests through the middleware pipeline.

        Args:
            request: FastAPI request object
            call_next: Next middleware/endpoint in chain

        Returns:
            Response object
        """
        # Cache registry lookup once for both _is_webhook_request and _get_endpoint_webhook_config
        if self.server and request.method in ["GET", "POST", "PUT", "PATCH"]:
            request.state._webhook_endpoints_match = (
                self.server._endpoint_registry.get_webhook_endpoints_matching_path(
                    request.url.path, request.method
                )
            )
        else:
            request.state._webhook_endpoints_match = None  # Fallback uses path check

        # Check if this is a webhook request
        if not self._is_webhook_request(request):
            # Not a webhook request, pass through normally
            return await call_next(request)

        t0 = time.perf_counter()
        logger.info(f"Processing webhook request: {request.url.path}")
        request.state.webhook_start = t0

        try:
            # Get endpoint-specific webhook configuration (uses cached match)
            webhook_config = self._get_endpoint_webhook_config(request)
            request.state.webhook_config = webhook_config

            # Process the webhook request with endpoint-specific config
            await self._process_webhook_request(request, webhook_config)
            logger.debug(
                f"Webhook: middleware done in {int((time.perf_counter() - t0) * 1000)}ms"
            )

            # Check for duplicate requests
            if getattr(request.state, "is_duplicate_request", False):
                cached_response = getattr(request.state, "cached_response", {})
                logger.debug(
                    f"Returning cached response for duplicate request: {request.state.idempotency_key}"
                )
                return JSONResponse(content=cached_response, status_code=200)

            # Handle async processing if enabled and background tasks allowed
            if (
                webhook_config
                and webhook_config.get("async_processing", False)
                and use_background_processing()
            ):
                # Queue for async processing and return immediate response
                task_id = self._queue_async_processing(request, call_next)
                from datetime import datetime

                response_data = {
                    "status": "queued",
                    "timestamp": datetime.now().isoformat(),
                    "message": "Webhook queued for asynchronous processing",
                    "task_id": task_id,
                }
                return JSONResponse(content=response_data, status_code=200)

            # Continue to the endpoint handler
            response = await call_next(request)

            # Store response for idempotency if needed
            idempotency_key = getattr(request.state, "idempotency_key", None)
            if idempotency_key and isinstance(response, JSONResponse):
                try:
                    response_content = (
                        response.body.decode("utf-8") if response.body else "{}"
                    )
                    response_data = json.loads(response_content)
                    if use_background_processing():
                        asyncio.create_task(
                            store_idempotent_response(idempotency_key, response_data)
                        )
                    else:
                        await store_idempotent_response(idempotency_key, response_data)
                except Exception as e:
                    logger.warning(f"Failed to cache response for idempotency: {e}")

            return response

        except HTTPException as e:
            # Convert HTTPException to proper webhook response
            logger.warning(f"Webhook processing failed: {e.detail}")
            from datetime import datetime

            error_response = {
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "message": e.detail,
                "error_code": e.status_code,
            }
            return JSONResponse(
                content=error_response, status_code=200
            )  # Always return 200 for webhooks

        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error in webhook middleware: {e}", exc_info=True)
            from datetime import datetime

            error_response = {
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "message": "Internal processing error",
                "error_code": 500,
            }
            return JSONResponse(
                content=error_response, status_code=200
            )  # Always return 200 for webhooks

    def _is_webhook_request(self, request: Request) -> bool:
        """Check if request is a webhook request.

        Uses registry-based detection when server is available: matches any
        registered endpoint with webhook=True. Falls back to path-prefix check
        when server is None (e.g. tests) for backward compatibility.

        Args:
            request: FastAPI request object

        Returns:
            True if this is a webhook request
        """
        if request.method not in ["GET", "POST", "PUT", "PATCH"]:
            return False

        # Use cached registry result when available (set in dispatch)
        endpoints = getattr(request.state, "_webhook_endpoints_match", None)
        if endpoints is not None:
            return len(endpoints) > 0

        # Registry-based detection when cache not set (e.g. server added mid-request)
        if self.server:
            endpoints = (
                self.server._endpoint_registry.get_webhook_endpoints_matching_path(
                    request.url.path, request.method
                )
            )
            if endpoints:
                return True

        # Fallback: path check for tests or when server is None.
        # Match paths containing /webhook/ or /webhook (e.g. /api/whatsapp/interact/webhook/{id})
        path = request.url.path
        api_prefix = (APIRoutes.PREFIX or "").rstrip("/")
        prefixed_pattern = (
            f"{api_prefix}/{self.webhook_path_pattern.lstrip('/')}"
            if api_prefix
            else None
        )
        return (
            path.startswith(self.webhook_path_pattern)
            or (prefixed_pattern is not None and path.startswith(prefixed_pattern))
            or "/webhook" in path
            or path.endswith("/webhook")
        )

    async def _process_webhook_request(
        self, request: Request, webhook_config: Optional[Dict[str, Any]] = None
    ) -> None:
        """Process webhook request and populate request.state.

        Args:
            request: FastAPI request object
            webhook_config: Endpoint-specific webhook configuration

        Raises:
            HTTPException: If processing fails
        """
        try:
            # Create config with endpoint-specific overrides
            config = self._create_processing_config(webhook_config)

            # Handle API key authentication if configured
            webhook_auth = (
                webhook_config.get("webhook_auth") if webhook_config else None
            )
            if webhook_auth == "api_key" or webhook_auth == "api_key_path":
                await authenticate_webhook_api_key(
                    request, webhook_auth, webhook_config, self.server
                )

            if request.method == "GET":
                # Light path for GET: no body, HMAC, or idempotency
                if config.https_required and request.url.scheme != "https":
                    raise HTTPException(
                        status_code=400,
                        detail="HTTPS required for webhook endpoints",
                    )
                request.state.raw_body = b""
                request.state.content_type = ""
                request.state.parsed_payload = dict(request.query_params)
                request.state.idempotency_key = None
                request.state.is_duplicate_request = False
                request.state.hmac_verified = False
                request.state.webhook_route = self._extract_route_parameter(request)
            else:
                # Full path for POST/PUT/PATCH
                # Skip idempotency for api_key webhooks without X-Idempotency-Key
                # (e.g. WhatsApp) to avoid unnecessary DB round-trips on Lambda
                skip_idempotency = (
                    webhook_config is not None
                    and webhook_config.get("webhook_auth")
                    in ("api_key", "api_key_path")
                    and extract_idempotency_key(request) is None
                )
                processed_data, cached_response = await validate_and_process_webhook(
                    request, config, skip_idempotency=skip_idempotency
                )

                # Populate request.state with processed data
                request.state.raw_body = processed_data["raw_body"]
                request.state.content_type = processed_data["content_type"]
                request.state.parsed_payload = processed_data.get("parsed_payload")
                request.state.idempotency_key = processed_data.get("idempotency_key")
                request.state.is_duplicate_request = processed_data["is_duplicate"]
                request.state.hmac_verified = processed_data["hmac_verified"]

                # Set cached response for duplicates
                if cached_response:
                    request.state.cached_response = cached_response

                # Extract route parameter if present in path
                request.state.webhook_route = self._extract_route_parameter(request)

            logger.debug(
                f"Webhook processing complete: "
                f"route={request.state.webhook_route}, "
                f"duplicate={request.state.is_duplicate_request}, "
                f"hmac_verified={request.state.hmac_verified}"
            )

        except HTTPException:
            # Re-raise HTTPExceptions as-is
            raise
        except Exception as e:
            logger.error(f"Failed to process webhook request: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail="Failed to process webhook request"
            )

    def _create_processing_config(
        self, webhook_config: Optional[Dict[str, Any]]
    ) -> WebhookConfig:
        """Create processing config with endpoint-specific overrides.

        Args:
            webhook_config: Endpoint-specific webhook configuration

        Returns:
            WebhookConfig for processing
        """
        base_config = self.config

        # Check server config for HTTPS requirement override
        https_required = base_config.https_required
        if self.server:
            server_config = getattr(self.server, "config", None)
            if server_config:
                # Check for webhook-specific HTTPS setting (nested config group)
                webhook_https_required = getattr(
                    server_config.webhook, "webhook_https_required", None
                )
                if webhook_https_required is not None:
                    https_required = webhook_https_required

        if not webhook_config:
            # No endpoint config (e.g. path-prefix fallback). Do not require HMAC
            # since we cannot determine if this webhook uses signature verification.
            return WebhookConfig(
                hmac_secret=None,
                hmac_algorithm=base_config.hmac_algorithm,
                max_payload_size=base_config.max_payload_size,
                idempotency_ttl=base_config.idempotency_ttl,
                https_required=https_required,
                allowed_content_types=base_config.allowed_content_types,
            )

        # Only require HMAC when endpoint has signature_required=True.
        # API-key-only webhooks (e.g. WhatsApp) do not send HMAC signatures.
        signature_required = webhook_config.get("signature_required", False)
        hmac_secret = None
        if signature_required:
            hmac_secret = webhook_config.get("hmac_secret") or base_config.hmac_secret

        # Create new config with endpoint-specific overrides
        return WebhookConfig(
            hmac_secret=hmac_secret,
            hmac_algorithm=base_config.hmac_algorithm,
            max_payload_size=base_config.max_payload_size,
            idempotency_ttl=webhook_config.get("idempotency_ttl_hours", 24)
            * 3600,  # Convert to seconds
            https_required=https_required,
            allowed_content_types=base_config.allowed_content_types,
        )

    async def _queue_async_processing(
        self, request: Request, call_next: Callable
    ) -> str:
        """Queue webhook for asynchronous processing.

        Args:
            request: FastAPI request object
            call_next: Next handler in chain

        Returns:
            Task ID for tracking
        """
        import asyncio
        import uuid

        task_id = str(uuid.uuid4())

        # Create async task for processing
        async def process_async():
            try:
                response = await call_next(request)
                logger.debug(f"Async webhook processing completed: {task_id}")
                return response
            except Exception as e:
                logger.error(
                    f"Async webhook processing failed: {task_id}, {e}", exc_info=True
                )
                raise

        # Queue the task (in production, use proper task queue like Celery)
        asyncio.create_task(process_async())

        logger.debug(f"Webhook queued for async processing: {task_id}")
        return task_id

    def _extract_route_parameter(self, request: Request) -> Optional[str]:
        """Extract route parameter from webhook URL path.

        Attempts to extract route from patterns like:
        - /webhook/{route}/{auth_token}
        - /webhooks/{route}/{auth_token}
        - /webhook/process/{route}/{auth_token}

        Args:
            request: FastAPI request object

        Returns:
            Route parameter if found, None otherwise
        """
        path = request.url.path
        path_parts = [p for p in path.split("/") if p]  # Remove empty parts

        try:
            # Find webhook segment (support both "webhook" and "webhooks")
            webhook_idx = None
            for i, part in enumerate(path_parts):
                if part in ("webhook", "webhooks"):
                    webhook_idx = i
                    break

            if webhook_idx is not None and len(path_parts) >= webhook_idx + 3:
                # Pattern: /webhook/{route}/{auth_token} or /webhooks/{route}/{auth_token}
                if len(path_parts) == webhook_idx + 3:
                    return str(path_parts[webhook_idx + 1])
                # Pattern: /webhook/process/{route}/{auth_token}
                if (
                    len(path_parts) >= webhook_idx + 4
                    and path_parts[webhook_idx + 1] == "process"
                ):
                    return str(path_parts[webhook_idx + 2])
                # Pattern: /webhook/{service}/{route}/{auth_token}
                if len(path_parts) >= webhook_idx + 4:
                    return str(path_parts[-2])

            return None

        except (IndexError, AttributeError):
            logger.warning(f"Failed to extract route from path: {path}")
            return None


# Convenience function for adding webhook middleware to FastAPI app
def add_webhook_middleware(
    app,
    config: Optional[WebhookConfig] = None,
    webhook_path_pattern: str = "/webhook/",
    server=None,
) -> None:
    """Add webhook middleware to FastAPI application.

    Args:
        app: FastAPI application instance
        config: Webhook configuration (uses env defaults if None)
        webhook_path_pattern: Path pattern to identify webhook requests
        server: Server instance for accessing endpoint metadata

    Example:
        ```python
        from fastapi import FastAPI
        from jvspatial.api.integrations.webhooks.middleware import add_webhook_middleware

        app = FastAPI()
        add_webhook_middleware(app)
        ```
    """
    app.add_middleware(
        WebhookMiddleware,
        config=config,
        webhook_path_pattern=webhook_path_pattern,
        server=server,
    )
    logger.info("Webhook middleware added to FastAPI application")


# Alternative class-based configuration
class WebhookMiddlewareConfig:
    """Configuration helper for WebhookMiddleware setup."""

    @staticmethod
    def create_production_config(
        hmac_secret: str,
        max_payload_size: int = 5 * 1024 * 1024,  # 5MB
        https_required: bool = True,
    ) -> WebhookConfig:
        """Create production webhook configuration.

        Args:
            hmac_secret: HMAC secret for signature verification
            max_payload_size: Maximum payload size in bytes
            https_required: Whether to require HTTPS

        Returns:
            WebhookConfig for production use
        """
        return WebhookConfig(
            hmac_secret=hmac_secret,
            max_payload_size=max_payload_size,
            https_required=https_required,
            idempotency_ttl=3600,  # 1 hour
        )

    @staticmethod
    def create_development_config() -> WebhookConfig:
        """Create development webhook configuration.

        Returns:
            WebhookConfig for development use (relaxed security)
        """
        return WebhookConfig(
            hmac_secret=None,  # No HMAC in development
            max_payload_size=10 * 1024 * 1024,  # 10MB
            https_required=False,  # Allow HTTP in development
            idempotency_ttl=300,  # 5 minutes
        )

    @staticmethod
    def create_testing_config() -> WebhookConfig:
        """Create testing webhook configuration.

        Returns:
            WebhookConfig for testing (minimal restrictions)
        """
        return WebhookConfig(
            hmac_secret="test-secret-key",  # pragma: allowlist secret
            max_payload_size=1024 * 1024,  # 1MB
            https_required=False,  # Allow HTTP in tests
            idempotency_ttl=60,  # 1 minute
        )


# Export main classes and functions
__all__ = ["WebhookMiddleware", "WebhookMiddlewareConfig", "add_webhook_middleware"]
