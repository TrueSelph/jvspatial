"""Event system for walker lifecycle hooks.

This module provides a minimal event emitter system for walker lifecycle
events and hooks.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List


class WalkerEventSystem:
    """Minimal event emitter for walker lifecycle hooks."""

    def __init__(self) -> None:
        """Initialize the event system."""
        self._handlers: Dict[str, List[Callable[..., Awaitable[Any]]]] = {}

    async def on(self, event: str, handler: Callable[..., Awaitable[Any]]) -> None:
        """Register an event handler.

        Args:
            event: Event name
            handler: Async handler function
        """
        self._handlers.setdefault(event, []).append(handler)

    async def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Emit an event to all registered handlers.

        Args:
            event: Event name
            *args: Positional arguments for handlers
            **kwargs: Keyword arguments for handlers
        """
        for handler in self._handlers.get(event, []):
            await handler(*args, **kwargs)
