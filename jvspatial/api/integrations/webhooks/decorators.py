"""Webhook endpoint decorators for jvspatial."""

from __future__ import annotations

from jvspatial.api.decorators.route import endpoint

# Webhook endpoint decorator (alias for endpoint with webhook-specific configuration)
webhook_endpoint = endpoint

__all__ = [
    "webhook_endpoint",
]
