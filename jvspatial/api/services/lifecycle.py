"""Lifecycle management service for jvspatial Server.

This module provides centralized lifecycle management including startup/shutdown
hooks, database initialization, file storage verification, and package discovery.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncGenerator, Callable, List

from fastapi import FastAPI

from jvspatial.api.constants import LogIcons
from jvspatial.core.entities import Root

if TYPE_CHECKING:
    from jvspatial.api.server import Server


class LifecycleManager:
    """Service for managing application lifecycle (startup/shutdown).

    This service centralizes all startup and shutdown logic including:
    - Database initialization through GraphContext
    - File storage verification
    - Package discovery
    - User-defined hooks execution
    - Application state tracking

    Attributes:
        server: Reference to the Server instance
        _startup_hooks: List of registered startup hooks
        _shutdown_hooks: List of registered shutdown hooks
        _is_started: Flag tracking startup state
    """

    def __init__(self, server: "Server") -> None:
        """Initialize the lifecycle manager.

        Args:
            server: Server instance this manager belongs to
        """
        self.server = server
        self._startup_hooks: List[Callable] = []
        self._shutdown_hooks: List[Callable] = []
        self._is_started = False
        self._logger = logging.getLogger(__name__)

    def add_startup_hook(self, func: Callable) -> Callable:
        """Register a startup hook.

        Args:
            func: Function to run on startup

        Returns:
            The function (for decorator pattern)
        """
        self._startup_hooks.append(func)
        return func

    def add_shutdown_hook(self, func: Callable) -> Callable:
        """Register a shutdown hook.

        Args:
            func: Function to run on shutdown

        Returns:
            The function (for decorator pattern)
        """
        self._shutdown_hooks.append(func)
        return func

    async def startup(self) -> None:
        """Execute startup sequence.

        This method performs:
        1. Sets running state
        2. Initializes database through GraphContext
        3. Ensures root node exists
        4. Verifies file storage if enabled
        5. Runs user-defined startup hooks

        Note: Endpoint discovery runs before app creation in _create_app_instance(),
        not during startup, to ensure all endpoints are registered before routers
        are included in the FastAPI app.
        """
        # Set running state
        self.server._is_running = True
        self._is_started = True

        # Initialize database through GraphContext
        await self._initialize_database()

        # Verify file storage if enabled
        await self._verify_file_storage()

        # Run user-defined startup hooks
        await self._execute_startup_hooks()

    async def _initialize_database(self) -> None:
        """Initialize database and ensure root node exists."""
        try:
            if self.server._graph_context:
                # Use explicit GraphContext
                db_type = type(self.server._graph_context.database).__name__
            else:
                # Use default GraphContext behavior
                db_type = "default"

            # Ensure root node exists - Root.get() always returns singleton
            root = await Root.get()

            # Log concise database initialization
            self._logger.info(
                f"{LogIcons.DATABASE} Database: {db_type} | {LogIcons.TREE} Root: {root.id}"
            )

        except Exception as e:
            self._logger.error(f"{LogIcons.ERROR} Database initialization failed: {e}")
            raise

    async def _verify_file_storage(self) -> None:
        """Verify file storage configuration if enabled."""
        if self.server.config.file_storage.file_storage_enabled:
            storage_info = f"{self.server.config.file_storage.file_storage_provider}@{self.server.config.file_storage.file_storage_root}"
            if self.server.config.proxy.proxy_enabled:
                storage_info += " | proxy enabled"
            self._logger.info(f"{LogIcons.STORAGE} Storage: {storage_info}")

    async def _execute_startup_hooks(self) -> None:
        """Execute all registered startup hooks."""
        for task in self._startup_hooks:
            try:
                if asyncio.iscoroutinefunction(task):
                    await task()
                else:
                    task()
            except Exception as e:
                self._logger.error(f"{LogIcons.ERROR} Startup task failed: {e}")

    async def shutdown(self) -> None:
        """Execute shutdown sequence.

        This method performs:
        1. Runs user-defined shutdown hooks
        2. Clears running state
        3. Logs shutdown event
        """
        self._logger.info(
            f"{LogIcons.STOP} Shutting down {self.server.config.title}..."
        )

        # Run user-defined shutdown hooks
        await self._execute_shutdown_hooks()

        # Clear running state
        self.server._is_running = False
        self._is_started = False

    async def _execute_shutdown_hooks(self) -> None:
        """Execute all registered shutdown hooks."""
        for task in self._shutdown_hooks:
            try:
                if asyncio.iscoroutinefunction(task):
                    await task()
                else:
                    task()
            except Exception as e:
                self._logger.error(f"{LogIcons.ERROR} Shutdown task failed: {e}")

    @asynccontextmanager
    def lifespan(self, app: FastAPI) -> AsyncGenerator[None, None]:
        """Async context manager for FastAPI lifespan.

        This context manager handles the complete application lifecycle:
        - On entry: Runs startup sequence
        - On exit: Runs shutdown sequence

        Args:
            app: FastAPI application instance

        Yields:
            None (application running state)
        """

        async def _lifespan():
            # Startup
            await self.startup()

            yield  # Application is running

            # Shutdown
            await self.shutdown()

        return _lifespan()

    @property
    def is_running(self) -> bool:
        """Check if application is running.

        Returns:
            True if running, False otherwise
        """
        return self._is_started


__all__ = ["LifecycleManager"]
