"""Registry and dispatch for serverless deferred tasks delivered via HTTP (e.g. LWA)."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

logger = logging.getLogger(__name__)

DeferredHandler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]
_handlers: Dict[str, DeferredHandler] = {}


class UnknownDeferredTaskError(LookupError):
    """No handler registered for ``task_type``."""

    def __init__(self, task_type: str) -> None:
        self.task_type = task_type
        super().__init__(task_type)


class MalformedDeferredInvokeError(ValueError):
    """Request body is not a valid deferred-invoke envelope."""


def register_deferred_invoke_handler(task_type: str, fn: DeferredHandler) -> None:
    """Register an async handler for ``task_type`` (e.g. ``app.whatsapp.media_batch``)."""
    if task_type in _handlers:
        logger.warning(
            "Overwriting deferred invoke handler for task_type=%s", task_type
        )
    _handlers[task_type] = fn


def deferred_invoke_handler(
    task_type: str,
) -> Callable[[DeferredHandler], DeferredHandler]:
    """Decorator equivalent of :func:`register_deferred_invoke_handler`."""

    def decorator(fn: DeferredHandler) -> DeferredHandler:
        register_deferred_invoke_handler(task_type, fn)
        return fn

    return decorator


def clear_deferred_invoke_handlers() -> None:
    """Clear registry (for tests)."""
    _handlers.clear()


def normalize_deferred_envelope(body: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten SQS scheduler shape to the same dict layout as Lambda/LWA invoke.

    ``AwsSqsTaskScheduler`` sends ``{"task_type", "payload": {...}, ...}``.
    ``dispatch_deferred_invoke`` expects ``task_type`` at the top level with
    task fields merged (matching ``AwsLambdaDeferredTaskScheduler`` bodies).

    Idempotent: already-flat Lambda-style bodies are returned unchanged.
    """
    if not isinstance(body, dict):
        raise MalformedDeferredInvokeError("event must be a dict")
    task_type = body.get("task_type")
    if not task_type or not isinstance(task_type, str):
        raise MalformedDeferredInvokeError("missing or invalid task_type")
    payload = body.get("payload")
    if payload is None or not isinstance(payload, dict):
        return body
    merged: Dict[str, Any] = {**payload, "task_type": task_type}
    for key in ("process_at", "run_at", "reference", "retry"):
        if key in body and key not in merged:
            merged[key] = body[key]
    return merged


async def dispatch_deferred_invoke(event: Dict[str, Any]) -> Dict[str, Any]:
    """Run the handler for ``event['task_type']`` and return its JSON-serializable dict."""
    if not isinstance(event, dict):
        raise MalformedDeferredInvokeError("event must be a dict")
    event = normalize_deferred_envelope(event)
    task_type = event.get("task_type")
    if not task_type or not isinstance(task_type, str):
        raise MalformedDeferredInvokeError("missing or invalid task_type")
    handler = _handlers.get(task_type)
    if handler is None:
        raise UnknownDeferredTaskError(task_type)
    return await handler(event)
