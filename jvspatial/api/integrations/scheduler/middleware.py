"""FastAPI middleware integration for the scheduler system.

This module provides middleware that integrates the scheduler service
with FastAPI's lifecycle management, ensuring proper startup and shutdown
of scheduled tasks.
"""

import logging
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .scheduler import SchedulerService


class SchedulerMiddleware(BaseHTTPMiddleware):
    """Middleware to integrate scheduler service with FastAPI lifecycle.

    This middleware manages the scheduler service lifecycle, starting it
    during application startup and stopping it during shutdown. It doesn't
    intercept requests but ensures the scheduler runs alongside the FastAPI
    application.

    The middleware is designed to be lightweight and only manage the
    scheduler lifecycle without affecting request processing performance.
    """

    def __init__(self, app, scheduler_service: SchedulerService):
        """Initialize the scheduler middleware.

        Args:
            app: FastAPI application instance
            scheduler_service: SchedulerService instance to manage
        """
        super().__init__(app)
        self.scheduler_service = scheduler_service
        self.logger = logging.getLogger(__name__)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process requests - just pass through to next middleware.

        The scheduler middleware doesn't need to intercept requests,
        it only manages the scheduler service lifecycle.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in the chain

        Returns:
            HTTP response from downstream middleware
        """
        # Simply pass through to next middleware
        # The real work is done in startup/shutdown hooks
        return await call_next(request)


def add_scheduler_to_app(app, scheduler_service: SchedulerService) -> None:
    """Add scheduler service to FastAPI app with proper lifecycle management.

    This function adds the scheduler middleware and sets up startup/shutdown
    event handlers to manage the scheduler service lifecycle.

    Args:
        app: FastAPI application instance
        scheduler_service: SchedulerService instance to integrate
    """
    logger = logging.getLogger(__name__)

    # Add the middleware
    app.add_middleware(SchedulerMiddleware, scheduler_service=scheduler_service)

    # Add startup event handler
    @app.on_event("startup")
    async def start_scheduler():
        """Start the scheduler service when FastAPI starts."""
        try:
            logger.info("Starting scheduler service...")
            scheduler_service.start()

            # Log scheduler status
            status = scheduler_service.get_status()
            logger.info(
                f"Scheduler started successfully - "
                f"{status['registered_tasks']} tasks registered"
            )
        except Exception as e:
            logger.error(f"Failed to start scheduler service: {e}")
            # Don't raise - let the app start even if scheduler fails

    # Add shutdown event handler
    @app.on_event("shutdown")
    async def stop_scheduler():
        """Stop the scheduler service when FastAPI shuts down."""
        try:
            logger.info("Stopping scheduler service...")
            scheduler_service.stop()
            logger.info("Scheduler service stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler service: {e}")


class SchedulerLifecycleManager:
    """Helper class for managing scheduler lifecycle in FastAPI apps.

    This class provides a convenient way to integrate scheduler services
    with FastAPI applications, handling all the necessary lifecycle events
    and middleware setup.
    """

    def __init__(self, scheduler_service: SchedulerService):
        """Initialize the lifecycle manager.

        Args:
            scheduler_service: SchedulerService instance to manage
        """
        self.scheduler_service = scheduler_service
        self.logger = logging.getLogger(__name__)
        self._is_started = False

    def integrate_with_app(self, app) -> None:
        """Integrate the scheduler with a FastAPI application.

        This method sets up all necessary middleware and event handlers
        to manage the scheduler lifecycle with the FastAPI app.

        Args:
            app: FastAPI application instance
        """
        # Add middleware
        app.add_middleware(
            SchedulerMiddleware, scheduler_service=self.scheduler_service
        )

        # Add startup handler
        @app.on_event("startup")
        async def startup_scheduler():
            await self.start()

        # Add shutdown handler
        @app.on_event("shutdown")
        async def shutdown_scheduler():
            await self.stop()

    async def start(self) -> None:
        """Start the scheduler service asynchronously.

        This method handles the async startup of the scheduler service,
        including error handling and logging.
        """
        if self._is_started:
            self.logger.info("Scheduler service is already started")
            return

        try:
            self.logger.info("Starting scheduler service...")

            # Start the scheduler (this returns immediately as it uses background thread)
            self.scheduler_service.start()
            self._is_started = True

            # Get and log status
            status = self.scheduler_service.get_status()
            self.logger.info(
                f"✅ Scheduler service started successfully\n"
                f"   • Registered tasks: {status['registered_tasks']}\n"
                f"   • Enabled tasks: {status['enabled_tasks']}\n"
                f"   • Scheduled jobs: {status['scheduled_jobs']}\n"
                f"   • Check interval: {self.scheduler_service.config.interval}s"
            )

        except Exception as e:
            self.logger.error(f"❌ Failed to start scheduler service: {e}")
            self._is_started = False
            # Don't re-raise - allow the application to start even if scheduler fails

    async def stop(self) -> None:
        """Stop the scheduler service asynchronously.

        This method handles the async shutdown of the scheduler service,
        ensuring all running tasks are properly cancelled.
        """
        if not self._is_started:
            self.logger.info("Scheduler service is already stopped")
            return

        try:
            self.logger.info("Stopping scheduler service...")

            # Get final statistics before stopping
            status = self.scheduler_service.get_status()
            if status["total_executions"] > 0:
                self.logger.info(
                    f"📊 Final scheduler statistics:\n"
                    f"   • Total executions: {status['total_executions']}\n"
                    f"   • Successful: {status['successful_executions']}\n"
                    f"   • Failed: {status['failed_executions']}\n"
                    f"   • Success rate: {status['success_rate']:.1%}\n"
                    f"   • Uptime: {status['uptime_seconds']:.0f}s"
                )

            # Stop the scheduler
            self.scheduler_service.stop()
            self._is_started = False

            self.logger.info("✅ Scheduler service stopped successfully")

        except Exception as e:
            self.logger.error(f"❌ Error stopping scheduler service: {e}")
            self._is_started = False

    @property
    def is_started(self) -> bool:
        """Check if the scheduler service is started.

        Returns:
            True if scheduler is running, False otherwise
        """
        return self._is_started and self.scheduler_service.is_running

    def get_status(self) -> dict:
        """Get current scheduler status.

        Returns:
            Dictionary containing scheduler status information
        """
        base_status = {
            "lifecycle_manager_started": self._is_started,
            "service_running": self.scheduler_service.is_running,
        }

        # Add scheduler service status
        service_status = self.scheduler_service.get_status()
        base_status.update(service_status)

        return base_status
