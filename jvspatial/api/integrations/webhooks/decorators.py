"""Webhook endpoint decorators for jvspatial."""

from __future__ import annotations

from jvspatial.api.decorators.route import endpoint

# Alias for backward compatibility
webhook_endpoint = endpoint

__all__ = [
    "webhook_endpoint",
]
