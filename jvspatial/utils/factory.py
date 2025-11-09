"""Plugin factory for dependency injection and configuration.

This module provides a simple plugin factory system for registering and
retrieving implementations based on names or environment variables.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

T = TypeVar("T")


class PluginFactory(Generic[T]):
    """Simple, explicit plugin factory with optional env-based default.

    - Register implementations by name
    - Retrieve by explicit name or environment variable fallback
    - Minimal API to keep usage consistent across subsystems
    """

    def __init__(self, default_env_var: str):
        """Initialize the plugin factory.

        Args:
            default_env_var: Environment variable name for default selection
        """
        self._registry: Dict[str, Type[T]] = {}
        self._default: Optional[str] = None
        self._env_var = default_env_var

    async def register(self, name: str, implementation: Type[T]) -> None:
        """Register a plugin implementation.

        Args:
            name: Plugin name
            implementation: Plugin implementation class
        """
        self._registry[name] = implementation

    async def unregister(self, name: str) -> None:
        """Unregister a plugin implementation.

        Args:
            name: Plugin name to unregister
        """
        self._registry.pop(name, None)

    async def get(self, name: Optional[str] = None, **kwargs: Any) -> T:
        """Get a plugin instance.

        Args:
            name: Plugin name (uses env var or default if None)
            **kwargs: Arguments to pass to plugin constructor

        Returns:
            Plugin instance

        Raises:
            ValueError: If no plugin is selected or plugin is unknown
        """
        selected = name or os.getenv(self._env_var) or self._default
        if not selected:
            raise ValueError(
                f"No plugin selected for {self._env_var}. "
                f"Registered: {sorted(self._registry.keys())}"
            )
        if selected not in self._registry:
            raise ValueError(
                f"Unknown plugin '{selected}' for {self._env_var}. "
                f"Registered: {sorted(self._registry.keys())}"
            )
        impl = self._registry[selected]
        return impl(**kwargs)  # type: ignore[misc]

    async def set_default(self, name: str) -> None:
        """Set the default plugin name.

        Args:
            name: Plugin name to use as default

        Raises:
            ValueError: If plugin is not registered
        """
        if name not in self._registry:
            raise ValueError(f"Unknown plugin '{name}'")
        self._default = name

    async def list_available(self) -> List[str]:
        """List all available plugin names.

        Returns:
            Sorted list of plugin names
        """
        return sorted(self._registry.keys())
