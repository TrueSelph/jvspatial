"""Simple Event Bus for Walker and Node Communication.

This module provides a streamlined event-driven communication system
for Walkers and Nodes to communicate during parallel execution.
"""

import asyncio
import logging
import weakref
from contextlib import suppress
from functools import wraps
from typing import Any, Callable, Dict, List, Protocol, cast

logger = logging.getLogger(__name__)


class EventHandlerProtocol(Protocol):
    """Protocol for event handler functions with metadata."""

    _is_event_handler: bool
    _event_types: List[str]

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the event handler function."""
        ...


class EventBus:
    """Simple event bus for walker and node communication."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}
        self._active_entities: weakref.WeakValueDictionary = (
            weakref.WeakValueDictionary()
        )
        self._lock = asyncio.Lock()

    async def register_entity(self, entity) -> None:
        """Register a walker or node for event handling."""
        if hasattr(entity, "id"):
            self._active_entities[entity.id] = entity

    async def unregister_entity(self, entity_id: str) -> None:
        """Unregister an entity from event handling."""
        self._active_entities.pop(entity_id, None)

    async def emit(
        self, event_type: str, data: Any = None, source_id: str = "system"
    ) -> int:
        """Emit an event to all registered handlers.

        Args:
            event_type: Type of event to emit
            data: Event data payload
            source_id: ID of the entity emitting the event

        Returns:
            Number of handlers that processed the event
        """
        handlers_called = 0

        # Call direct handlers for this event type
        for handler in self._handlers.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event_type, data, source_id)
                else:
                    handler(event_type, data, source_id)
                handlers_called += 1
            except Exception as e:
                logger.error(f"Error in event handler for {event_type}: {e}")

        # Call entity handlers that have @on_emit decorators
        async with self._lock:
            for entity_id, entity in list(self._active_entities.items()):
                if entity_id != source_id and hasattr(entity, "_event_handlers"):
                    for handler in entity._event_handlers.get(event_type, []):
                        try:
                            # Call handler with self, event_type, data, and source_id (matching @on_emit decorator expectations)
                            if asyncio.iscoroutinefunction(handler):
                                await handler(entity, event_type, data, source_id)
                            else:
                                handler(entity, event_type, data, source_id)
                            handlers_called += 1
                        except Exception as e:
                            logger.error(
                                f"Error in entity {entity_id} event handler: {e}"
                            )

        logger.debug(
            f"Event '{event_type}' from {source_id} handled by {handlers_called} handlers"
        )
        return handlers_called

    async def add_handler(self, event_type: str, handler: Callable) -> None:
        """Add a direct event handler for an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def remove_handler(self, event_type: str, handler: Callable) -> None:
        """Remove a direct event handler."""
        if event_type in self._handlers:
            with suppress(ValueError):
                self._handlers[event_type].remove(handler)

    async def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics."""
        return {
            "active_entities": len(self._active_entities),
            "event_types": list(self._handlers.keys()),
            "total_handlers": sum(
                len(handlers) for handlers in self._handlers.values()
            ),
        }


# Global event bus instance
event_bus = EventBus()


def on_emit(*event_types: str):
    """Decorator for methods to handle emitted events.

    Args:
        event_types: Event types to handle

    Example:
        ```python
        class MyWalker(Walker):
            @await on_emit("data_found")
            async def handle_data_found(self, event_type: str, data: Any, source_id: str):
                self.report(f"Received data from {source_id}: {data}")

            @await on_emit("status_update", "progress_report")
            async def handle_status(self, event_type: str, data: Any, source_id: str):
                print(f"Status from {source_id}: {data}")
        ```
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        # Mark function as event handler
        wrapper._is_event_handler = True  # type: ignore[attr-defined]
        wrapper._event_types = list(event_types)  # type: ignore[attr-defined]

        return cast(EventHandlerProtocol, wrapper)

    return decorator


async def emit_event(
    event_type: str, data: Any = None, source_id: str = "system"
) -> int:
    """Global function to emit events.

    Args:
        event_type: Type of event
        data: Event data
        source_id: Source entity ID

    Returns:
        Number of handlers called
    """
    return await event_bus.emit(event_type, data, source_id)


async def add_event_handler(event_type: str, handler: Callable) -> None:
    """Add a global event handler.

    Args:
        event_type: Event type to handle
        handler: Handler function (sync or async)

    Example:
        ```python
        def log_all_events(event_type: str, data: Any, source_id: str):
            print(f"Event: {event_type} from {source_id}")

        await add_event_handler("*", log_all_events)
        ```
    """
    await event_bus.add_handler(event_type, handler)
