"""Middleware, exception handlers, and lifecycle hook decorators for Server."""

from __future__ import annotations

from typing import Any, Callable, Type, Union


class ServerLifecycleMixin:
    """Register custom middleware, exception handlers, and startup/shutdown hooks."""

    def middleware(self, middleware_type: str = "http") -> Callable:
        """Add middleware to the application.

        Args:
            middleware_type: Type of middleware ("http" or "websocket")

        Returns:
            Decorator function for middleware
        """

        def decorator(func: Callable) -> Callable:
            self.middleware_manager._custom_middleware.append(
                {"func": func, "middleware_type": middleware_type}
            )

            return func

        return decorator

    def exception_handler(
        self, exc_class_or_status_code: Union[int, Type[Exception]]
    ) -> Callable:
        """Add exception handler.

        Args:
            exc_class_or_status_code: Exception class or HTTP status code

        Returns:
            Decorator function for exception handlers
        """

        def decorator(func: Callable) -> Callable:
            self._exception_handlers[exc_class_or_status_code] = func

            return func

        return decorator

    async def on_startup(self, func: Callable[[], Any]) -> Callable[[], Any]:
        """Register startup task.

        Args:
            func: Startup function

        Returns:
            The original function
        """
        return self.lifecycle_manager.add_startup_hook(func)

    async def on_shutdown(self, func: Callable[[], Any]) -> Callable[[], Any]:
        """Register shutdown task.

        Args:
            func: Shutdown function

        Returns:
            The original function
        """
        return self.lifecycle_manager.add_shutdown_hook(func)
