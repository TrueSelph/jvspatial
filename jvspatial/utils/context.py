"""Global context management utilities.

This module provides lightweight global context managers that support
override functionality for dependency injection and testing.
"""

from __future__ import annotations

import contextlib
from typing import Callable, Generic, Optional, TypeVar

T = TypeVar("T")


class GlobalContext(Generic[T]):
    """Lightweight global context manager with override support.

    Not thread-local or task-local by default to avoid hidden magic. Use
    explicit injection where possible; this provides a pragmatic global for
    legacy/ergonomic access and testing overrides.
    """

    def __init__(self, factory: Callable[[], T], name: str):
        """Initialize the global context.

        Args:
            factory: Factory function to create new instances
            name: Name for debugging/logging
        """
        self._instance: Optional[T] = None
        self._factory = factory
        self._name = name

    async def get(self) -> T:
        """Get the current instance, creating it if necessary."""
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    async def set(self, instance: T) -> None:
        """Set the current instance."""
        self._instance = instance

    async def clear(self) -> None:
        """Clear the current instance."""
        self._instance = None

    @contextlib.contextmanager
    async def override(self, instance: T):
        """Temporarily override the current instance.

        Args:
            instance: The instance to use during the override
        """
        old = self._instance
        self._instance = instance
        try:
            yield
        finally:
            self._instance = old
