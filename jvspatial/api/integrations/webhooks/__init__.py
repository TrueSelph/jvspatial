"""Webhook integration for jvspatial API.

Provides webhook event handling, HMAC verification, and middleware.

Note: Use @endpoint with webhook=True parameter for webhook endpoints.
"""

try:
    from .middleware import WebhookMiddleware  # noqa: F401
    from .models import WebhookEvent, WebhookIdempotencyKey  # noqa: F401

    __all__ = [
        "WebhookEvent",
        "WebhookIdempotencyKey",
        "WebhookMiddleware",
    ]
except ImportError:
    # Some webhook components may not be fully available
    __all__ = []
