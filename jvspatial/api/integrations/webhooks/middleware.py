"""Webhook middleware for JVspatial FastAPI integration.

This middleware handles all webhook-specific processing including:
- HMAC signature verification
- Idempotency key management
- Payload preprocessing and validation
- HTTPS enforcement
- Route parameter extraction
"""

import logging
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .utils import (
    WebhookConfig,
    get_webhook_config_from_env,
    store_idempotent_response,
    validate_and_process_webhook,
)

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
            logger.warning("HMAC verification disabled - no secret configured")

    def _get_endpoint_webhook_config(
        self, request: Request
    ) -> Optional[Dict[str, Any]]:
        """Extract webhook configuration from endpoint metadata.

        Args:
            request: FastAPI request object

        Returns:
            Dictionary with endpoint-specific webhook configuration or None
        """
        if not self.server:
            return None

        path = request.url.path
        method = request.method

        # Get all endpoints at this path from registry
        endpoints = self.server._endpoint_registry.get_by_path(path)

        for endpoint_info in endpoints:
            # Check if methods match
            if method not in endpoint_info.methods:
                continue

            # Check if endpoint requires webhook processing
            handler = endpoint_info.handler
            if getattr(handler, "_webhook_required", False):
                return self._extract_webhook_metadata(handler)

        return None

    def _path_matches(self, request_path: str, endpoint_path: str) -> bool:
        """Check if request path matches endpoint path pattern.

        Args:
            request_path: Actual request path
            endpoint_path: Endpoint path pattern (may include {param})

        Returns:
            True if paths match
        """
        if not endpoint_path:
            return False

        # Simple pattern matching for {param} style paths
        import re

        pattern = re.sub(r"\{[^}]+\}", "[^/]+", endpoint_path)
        pattern = f"^{pattern}$"
        return bool(re.match(pattern, request_path))

    def _extract_webhook_metadata(self, endpoint_obj) -> Dict[str, Any]:
        """Extract webhook metadata from endpoint function or walker class.

        Args:
            endpoint_obj: Function or Walker class with webhook metadata

        Returns:
            Dictionary with webhook configuration
        """
        return {
            "hmac_secret": getattr(endpoint_obj, "_hmac_secret", None),
            "idempotency_key_field": getattr(
                endpoint_obj, "_idempotency_key_field", "X-Idempotency-Key"
            ),
            "idempotency_ttl_hours": getattr(
                endpoint_obj, "_idempotency_ttl_hours", 24
            ),
            "async_processing": getattr(endpoint_obj, "_async_processing", False),
            "path_key_auth": getattr(endpoint_obj, "_path_key_auth", False),
            "auth_required": getattr(endpoint_obj, "_auth_required", False),
            "required_permissions": getattr(endpoint_obj, "_required_permissions", []),
            "required_roles": getattr(endpoint_obj, "_required_roles", []),
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process webhook requests through the middleware pipeline.

        Args:
            request: FastAPI request object
            call_next: Next middleware/endpoint in chain

        Returns:
            Response object
        """
        # Check if this is a webhook request
        if not self._is_webhook_request(request):
            # Not a webhook request, pass through normally
            return await call_next(request)

        logger.debug(f"Processing webhook request: {request.url.path}")

        try:
            # Get endpoint-specific webhook configuration
            webhook_config = self._get_endpoint_webhook_config(request)
            request.state.webhook_config = webhook_config

            # Process the webhook request with endpoint-specific config
            await self._process_webhook_request(request, webhook_config)

            # Check for duplicate requests
            if getattr(request.state, "is_duplicate_request", False):
                cached_response = getattr(request.state, "cached_response", {})
                logger.info(
                    f"Returning cached response for duplicate request: {request.state.idempotency_key}"
                )
                return JSONResponse(content=cached_response, status_code=200)

            # Handle async processing if enabled
            if webhook_config and webhook_config.get("async_processing", False):
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
            response = call_next(request)

            # Store response for idempotency if needed
            idempotency_key = getattr(request.state, "idempotency_key", None)
            if idempotency_key and isinstance(response, JSONResponse):
                try:
                    # Extract response content for caching
                    response_content = (
                        response.body.decode("utf-8") if response.body else "{}"
                    )
                    import json

                    response_data = json.loads(response_content)
                    # Note: This should be awaited in an async context, but response processing
                    # happens after the main request handling, so we'll use create_task
                    import asyncio

                    asyncio.create_task(
                        store_idempotent_response(idempotency_key, response_data)
                    )
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

        Args:
            request: FastAPI request object

        Returns:
            True if this is a webhook request
        """
        path = request.url.path
        return path.startswith(self.webhook_path_pattern) and request.method in [
            "POST",
            "PUT",
            "PATCH",
        ]  # Typical webhook methods

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

            # Handle path-based authentication if enabled
            if webhook_config and webhook_config.get("path_key_auth", False):
                await self._handle_path_based_auth(request)

            # Use the utility function for comprehensive processing
            processed_data, cached_response = await validate_and_process_webhook(
                request, config
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

        if not webhook_config:
            return base_config

        # Create new config with endpoint-specific overrides
        return WebhookConfig(
            hmac_secret=webhook_config.get("hmac_secret") or base_config.hmac_secret,
            hmac_algorithm=base_config.hmac_algorithm,
            max_payload_size=base_config.max_payload_size,
            idempotency_ttl=webhook_config.get("idempotency_ttl_hours", 24)
            * 3600,  # Convert to seconds
            https_required=base_config.https_required,
            allowed_content_types=base_config.allowed_content_types,
        )

    async def _handle_path_based_auth(self, request: Request) -> None:
        """Handle path-based authentication using API keys.

        This method extracts the API key from the URL path and validates it
        against the authentication system. The key format is expected to be
        'key_id:secret' in the last path segment.

        Args:
            request: FastAPI request object

        Raises:
            HTTPException: If authentication fails (400 for format errors, 401 for auth failures)
        """
        try:
            # Extract {key} parameter from path
            path_parts = request.url.path.strip("/").split("/")

            if len(path_parts) < 2:
                raise HTTPException(
                    status_code=400, detail="Invalid webhook path format"
                )

            # Last path segment is the key
            key_param = path_parts[-1]

            if ":" not in key_param:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid API key format (expected key_id:secret)",
                )

            # Use basic API key validation for path-based auth
            # This avoids coupling to the full auth middleware
            await self._validate_api_key_basic(request, key_param)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Path-based authentication failed: {e}", exc_info=True)
            raise HTTPException(status_code=401, detail="Authentication failed")

    async def _validate_api_key_basic(self, request: Request, key_param: str) -> None:
        """Basic API key validation when auth middleware is not available.

        This is a fallback method that performs minimal validation.
        In production, proper authentication should be implemented.

        Args:
            request: FastAPI request object
            key_param: API key parameter (format: key_id:secret)

        Raises:
            HTTPException: If validation fails
        """
        # Split key into components
        parts = key_param.split(":", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Invalid API key format")

        key_id, secret = parts

        # Basic validation - ensure both parts are non-empty
        if not key_id or not secret:
            raise HTTPException(
                status_code=400, detail="API key ID and secret cannot be empty"
            )

        # For basic validation, we'll create a minimal user object
        # In production, this should query a database or cache
        from types import SimpleNamespace

        basic_user = SimpleNamespace(
            id=key_id,
            is_active=True,
            api_key_validated=True,
            authentication_method="api_key_basic",
        )

        request.state.current_user = basic_user
        logger.info(f"Basic API key validation successful for key_id: {key_id}")

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
                response = call_next(request)
                logger.info(f"Async webhook processing completed: {task_id}")
                return response
            except Exception as e:
                logger.error(
                    f"Async webhook processing failed: {task_id}, {e}", exc_info=True
                )
                raise

        # Queue the task (in production, use proper task queue like Celery)
        asyncio.create_task(process_async())

        logger.info(f"Webhook queued for async processing: {task_id}")
        return task_id

    def _extract_route_parameter(self, request: Request) -> Optional[str]:
        """Extract route parameter from webhook URL path.

        Attempts to extract route from patterns like:
        - /webhook/{route}/{auth_token}
        - /webhook/process/{route}/{auth_token}

        Args:
            request: FastAPI request object

        Returns:
            Route parameter if found, None otherwise
        """
        path = request.url.path
        path_parts = [p for p in path.split("/") if p]  # Remove empty parts

        try:
            # Look for common webhook patterns
            if len(path_parts) >= 3 and path_parts[0] == "webhooks":
                # Pattern: /webhook/{route}/{auth_token}
                if len(path_parts) == 3:
                    return str(path_parts[1])  # route is second part
                # Pattern: /webhook/process/{route}/{auth_token}
                elif len(path_parts) == 4 and path_parts[1] == "process":
                    return str(path_parts[2])  # route is third part
                # Pattern: /webhook/{service}/{route}/{auth_token}
                elif len(path_parts) >= 4:
                    # Could be service or route - prefer route (second-to-last non-token)
                    return str(path_parts[-2])  # Second to last (before auth_token)

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
        from jvspatial.api.webhook.middleware import add_webhook_middleware

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
