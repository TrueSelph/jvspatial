"""Webhook-specific endpoint helpers for JVspatial.

This module provides helper functions and response handlers specifically
designed for webhook endpoints, including payload injection and response formatting.
"""

import asyncio
import inspect
from typing import Any, Callable, Dict, Optional

from fastapi import Request

from jvspatial.api.endpoint.response import EndpointResponseHelper as EndpointHelper
from jvspatial.core.entities import Walker


class WebhookEndpointHelper(EndpointHelper):
    """Extended endpoint helper for webhook endpoints."""

    def __init__(self, walker_instance: Optional[Walker] = None):
        """Initialize webhook endpoint helper.

        Args:
            walker_instance: Walker instance if this is a walker endpoint
        """
        super().__init__(walker_instance)
        self.webhook_data: Dict[str, Any] = {}

    def webhook_response(
        self,
        status: str = "received",
        message: Optional[str] = None,
        task_id: Optional[str] = None,
        **data,
    ) -> Dict[str, Any]:
        """Create standardized webhook response.

        Args:
            status: Webhook processing status (received, processed, queued, error)
            message: Optional status message
            task_id: Optional task ID for async processing
            **data: Additional response data

        Returns:
            Standardized webhook response dictionary
        """
        response = self.success(data={"status": status, **data})

        if message:
            response["message"] = message

        if task_id:
            response["task_id"] = task_id

        return response

    def webhook_error(
        self, message: str, error_code: Optional[int] = None, **data
    ) -> Dict[str, Any]:
        """Create standardized webhook error response.

        Args:
            message: Error message
            error_code: Optional error code
            **data: Additional error data

        Returns:
            Standardized webhook error response
        """
        response = self.error(message=message, **data)

        if error_code:
            response["error_code"] = error_code

        return response


def create_webhook_endpoint_helper(
    walker_instance: Optional[Walker] = None, request: Optional[Request] = None
) -> WebhookEndpointHelper:
    """Create webhook-specific endpoint helper.

    Args:
        walker_instance: Walker instance if this is a walker endpoint
        request: FastAPI request object with webhook state

    Returns:
        WebhookEndpointHelper instance
    """
    helper = WebhookEndpointHelper(walker_instance)

    if request:
        # Inject webhook-specific data from request state
        helper.webhook_data = {
            "raw_body": getattr(request.state, "raw_body", b""),
            "content_type": getattr(request.state, "content_type", ""),
            "parsed_payload": getattr(request.state, "parsed_payload", None),
            "idempotency_key": getattr(request.state, "idempotency_key", None),
            "webhook_route": getattr(request.state, "webhook_route", None),
            "hmac_verified": getattr(request.state, "hmac_verified", False),
            "webhook_config": getattr(request.state, "webhook_config", {}),
        }

    return helper


def inject_webhook_payload(func: Callable) -> Callable:
    """Decorator to inject webhook payload into function parameters.

    This decorator automatically injects webhook data as function parameters
    based on parameter names and types.

    Args:
        func: Function to inject payload into

    Returns:
        Wrapped function with payload injection
    """
    sig = inspect.signature(func)

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Get request from args or kwargs
        request = None
        for arg in args:
            if hasattr(arg, "state") and hasattr(arg, "url"):
                request = arg
                break

        if not request:
            request = kwargs.get("request")

        if not request:
            # No request available, call function as-is
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        # Inject webhook data based on parameter names
        for param_name, _param in sig.parameters.items():
            if param_name in kwargs:
                continue  # Already provided

            # Inject based on parameter name
            if param_name == "payload":
                kwargs["payload"] = getattr(request.state, "parsed_payload", {})
            elif param_name == "raw_body":
                kwargs["raw_body"] = getattr(request.state, "raw_body", b"")
            elif param_name == "content_type":
                kwargs["content_type"] = getattr(request.state, "content_type", "")
            elif param_name == "endpoint":
                kwargs["endpoint"] = create_webhook_endpoint_helper(request=request)
            elif param_name == "webhook_data":
                kwargs["webhook_data"] = {
                    "raw_body": getattr(request.state, "raw_body", b""),
                    "content_type": getattr(request.state, "content_type", ""),
                    "parsed_payload": getattr(request.state, "parsed_payload", None),
                    "idempotency_key": getattr(request.state, "idempotency_key", None),
                    "webhook_route": getattr(request.state, "webhook_route", None),
                }

        # Call the function
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)

    return wrapper


def inject_walker_webhook_payload(walker_class: type) -> type:
    """Decorator to inject webhook payload into Walker class constructor.

    This decorator modifies Walker class initialization to accept webhook payload
    data and make it available as instance attributes.

    Args:
        walker_class: Walker class to modify

    Returns:
        Modified Walker class with payload injection
    """
    original_init = walker_class.__init__  # type: ignore

    def enhanced_init(self, *args: Any, **kwargs: Any) -> None:
        # Extract webhook data from kwargs if present
        webhook_data = kwargs.pop("webhook_data", {})

        # Call original constructor
        original_init(self, *args, **kwargs)

        # Set webhook data as instance attributes
        self.raw_body = webhook_data.get("raw_body", b"")
        self.content_type = webhook_data.get("content_type", "")
        self.parsed_payload = webhook_data.get("parsed_payload")
        self.payload = self.parsed_payload  # Convenient alias
        self.idempotency_key = webhook_data.get("idempotency_key")
        self.webhook_route = webhook_data.get("webhook_route")
        self.hmac_verified = webhook_data.get("hmac_verified", False)

        # Convenient access to webhook data
        self.webhook_data = webhook_data

    walker_class.__init__ = enhanced_init  # type: ignore
    return walker_class


def create_webhook_wrapper(endpoint_func: Callable) -> Callable:
    """Create a wrapper for webhook endpoint functions.

    This wrapper handles payload injection and response formatting for webhook endpoints.

    Args:
        endpoint_func: Original endpoint function

    Returns:
        Wrapped function with webhook handling
    """

    @inject_webhook_payload
    async def webhook_wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
        try:
            # Create webhook endpoint helper
            endpoint_helper = create_webhook_endpoint_helper(request=request)

            # Add endpoint helper to kwargs if expected
            sig = inspect.signature(endpoint_func)
            if "endpoint" in sig.parameters:
                kwargs["endpoint"] = endpoint_helper

            # Call original function
            if asyncio.iscoroutinefunction(endpoint_func):
                result = await endpoint_func(request, *args, **kwargs)
            else:
                result = endpoint_func(request, *args, **kwargs)

            # Format response if it's a plain dict
            if isinstance(result, dict) and "status" not in result:
                result = endpoint_helper.webhook_response(**result)

            return result

        except Exception as e:
            # Create error response
            endpoint_helper = create_webhook_endpoint_helper(request=request)
            return endpoint_helper.webhook_error(message=str(e), error_code=500)

    # Preserve function metadata
    webhook_wrapper.__name__ = endpoint_func.__name__
    webhook_wrapper.__doc__ = endpoint_func.__doc__

    return webhook_wrapper


def create_webhook_walker_wrapper(walker_class: type) -> Callable:
    """Create a wrapper for webhook walker endpoints.

    This wrapper handles payload injection and walker instantiation for webhook endpoints.

    Args:
        walker_class: Walker class to wrap

    Returns:
        Wrapped function that creates and executes walker with webhook data
    """
    # Apply webhook payload injection to the walker class
    enhanced_walker_class = inject_walker_webhook_payload(walker_class)

    async def webhook_walker_wrapper(
        request: Request, *args: Any, **kwargs: Any
    ) -> Any:
        try:
            # Extract webhook data from request state
            webhook_data = {
                "raw_body": getattr(request.state, "raw_body", b""),
                "content_type": getattr(request.state, "content_type", ""),
                "parsed_payload": getattr(request.state, "parsed_payload", None),
                "idempotency_key": getattr(request.state, "idempotency_key", None),
                "webhook_route": getattr(request.state, "webhook_route", None),
                "hmac_verified": getattr(request.state, "hmac_verified", False),
            }

            # Create walker instance with webhook data
            walker = enhanced_walker_class(*args, webhook_data=webhook_data, **kwargs)

            # Execute walker (this would normally go through the graph system)
            # For now, create a simple response
            result = {
                "status": "processed",
                "walker": walker_class.__name__,
                "webhook_route": webhook_data.get("webhook_route"),
                "hmac_verified": webhook_data.get("hmac_verified", False),
            }

            # If walker has response attribute, use it
            if hasattr(walker, "response") and walker.response:
                result.update(walker.response)

            return result

        except Exception as e:
            # Create error response
            return {
                "status": "error",
                "message": str(e),
                "error_code": 500,
                "walker": walker_class.__name__,
            }

    # Preserve class metadata
    webhook_walker_wrapper.__name__ = f"{walker_class.__name__}_webhook_wrapper"
    webhook_walker_wrapper.__doc__ = walker_class.__doc__

    return webhook_walker_wrapper


# Export main functions
__all__ = [
    "WebhookEndpointHelper",
    "create_webhook_endpoint_helper",
    "inject_webhook_payload",
    "inject_walker_webhook_payload",
    "create_webhook_wrapper",
    "create_webhook_walker_wrapper",
]
