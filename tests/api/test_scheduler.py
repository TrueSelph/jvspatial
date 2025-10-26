"""Tests for the scheduler integration.

These tests verify that the scheduler service, decorators, and middleware
work correctly with and without the schedule package.
"""

import asyncio
import time
from unittest.mock import Mock, patch

import pytest

# Test availability checking first
try:
    from jvspatial.api.integrations.scheduler.scheduler import SCHEDULE_AVAILABLE

    SCHEDULER_TESTS_ENABLED = SCHEDULE_AVAILABLE
except ImportError:
    SCHEDULER_TESTS_ENABLED = False


@pytest.mark.skipif(
    not SCHEDULER_TESTS_ENABLED, reason="Schedule package not available"
)
class TestSchedulerIntegration:
    """Test scheduler integration when schedule package is available."""

    async def test_scheduler_availability(self):
        """Test that scheduler is properly detected as available."""
        from jvspatial.api.integrations.scheduler.scheduler import SCHEDULE_AVAILABLE

        assert SCHEDULE_AVAILABLE is True

    async def test_scheduler_service_creation(self):
        """Test creating a scheduler service."""
        from jvspatial.api.integrations.scheduler.scheduler import (
            SchedulerConfig,
            SchedulerService,
        )

        config = SchedulerConfig(enabled=True, interval=1)
        scheduler = SchedulerService(config=config)

        assert scheduler.config.enabled is True
        assert scheduler.config.interval == 1
        assert scheduler.is_running is False

    async def test_on_schedule_decorator(self):
        """Test the @on_schedule decorator."""
        from jvspatial.api.integrations.scheduler.scheduler import (
            get_schedule_info,
            is_scheduled,
            on_schedule,
        )

        @on_schedule("every 10 seconds", description="Test task")
        async def test_task():
            return "test result"

        # Test function metadata
        assert is_scheduled(test_task) is True

        schedule_info = get_schedule_info(test_task)
        assert schedule_info is not None
        assert schedule_info["schedule"] == "every 10 seconds"
        assert schedule_info["description"] == "Test task"

        # Test function execution
        result = await test_task()
        assert result == "test result"

    async def test_scheduler_registry(self):
        """Test the decorator registry functionality."""
        from jvspatial.api.integrations.scheduler.scheduler import (
            clear_scheduled_registry,
            get_scheduled_tasks,
            on_schedule,
        )

        # Clear registry first
        clear_scheduled_registry()
        assert len(get_scheduled_tasks()) == 0

        # Add a scheduled task
        @on_schedule("every 5 minutes", task_id="test_registry_task")
        def registry_test():
            pass

        tasks = get_scheduled_tasks()
        assert len(tasks) == 1
        assert "test_registry_task" in tasks

        # Clean up
        clear_scheduled_registry()

    async def test_task_registration_with_scheduler(self):
        """Test registering decorated tasks with scheduler service."""
        from jvspatial.api.integrations.scheduler.scheduler import (
            SchedulerConfig,
            SchedulerService,
            clear_scheduled_registry,
            on_schedule,
            register_scheduled_tasks,
        )

        # Clear registry first
        clear_scheduled_registry()

        # Create scheduler
        config = SchedulerConfig(enabled=True, interval=1)
        scheduler = SchedulerService(config=config)

        # Define a task
        @on_schedule("every 30 seconds", task_id="registration_test")
        def registration_test_task():
            return "registered"

        # Register tasks
        register_scheduled_tasks(scheduler)

        # Check that task was registered
        tasks = scheduler.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].task_id == "registration_test"

        # Clean up
        clear_scheduled_registry()

    async def test_scheduler_lifecycle(self):
        """Test starting and stopping the scheduler."""
        from jvspatial.api.integrations.scheduler.scheduler import (
            SchedulerConfig,
            SchedulerService,
        )

        config = SchedulerConfig(
            enabled=True, interval=0.1
        )  # Fast interval for testing
        scheduler = SchedulerService(config=config)

        # Test starting
        scheduler.start()
        assert scheduler.is_running is True

        # Let it run briefly
        time.sleep(0.2)

        # Test stopping
        scheduler.stop()
        assert scheduler.is_running is False

    async def test_scheduler_status(self):
        """Test getting scheduler status information."""
        from jvspatial.api.integrations.scheduler.scheduler import (
            SchedulerConfig,
            SchedulerService,
            clear_scheduled_registry,
            on_schedule,
            register_scheduled_tasks,
        )

        # Clear registry and create scheduler
        clear_scheduled_registry()
        config = SchedulerConfig(enabled=True, interval=1)
        scheduler = SchedulerService(config=config)

        # Add a task
        @on_schedule("every 1 minute", task_id="status_test")
        def status_test_task():
            pass

        register_scheduled_tasks(scheduler)

        # Get status
        status = scheduler.get_status()

        assert "registered_tasks" in status
        assert "enabled_tasks" in status
        assert "scheduled_jobs" in status
        assert "is_running" in status
        assert status["registered_tasks"] == 1
        assert status["is_running"] is False

        # Clean up
        clear_scheduled_registry()

    @pytest.mark.asyncio
    async def test_middleware_lifecycle_manager(self):
        """Test the scheduler lifecycle manager."""
        from jvspatial.api.integrations.scheduler.scheduler import (
            SchedulerConfig,
            SchedulerLifecycleManager,
            SchedulerService,
        )

        config = SchedulerConfig(enabled=True, interval=1)
        scheduler = SchedulerService(config=config)
        lifecycle_manager = SchedulerLifecycleManager(scheduler)

        # Test starting
        await lifecycle_manager.start()
        assert lifecycle_manager.is_started is True
        assert scheduler.is_running is True

        # Test stopping
        await lifecycle_manager.stop()
        assert lifecycle_manager.is_started is False
        assert scheduler.is_running is False


class TestSchedulerUnavailable:
    """Test behavior when schedule package is not available."""

    @patch("jvspatial.api.integrations.scheduler.scheduler.SCHEDULE_AVAILABLE", False)
    async def test_import_error_when_unavailable(self):
        """Test that helpful errors are raised when schedule is unavailable."""
        # This test simulates the schedule package not being available
        # We can't easily test the actual import failure, but we can test
        # that the error factories work correctly
        from jvspatial.api.integrations.scheduler.scheduler import (
            _missing_dependency_factory,
        )

        missing_class = _missing_dependency_factory("TestClass")

        with pytest.raises(ImportError, match="requires the schedule package"):
            missing_class()

    async def test_schedule_available_flag(self):
        """Test that the SCHEDULE_AVAILABLE flag is accessible."""
        from jvspatial.api.integrations.scheduler.scheduler import SCHEDULE_AVAILABLE

        assert isinstance(SCHEDULE_AVAILABLE, bool)


class TestSchedulerUtilities:
    """Test utility functions."""

    @pytest.mark.skipif(
        not SCHEDULER_TESTS_ENABLED, reason="Schedule package not available"
    )
    async def test_default_scheduler_management(self):
        """Test setting and getting default scheduler."""
        from jvspatial.api.integrations.scheduler.scheduler import (
            SchedulerConfig,
            SchedulerService,
            get_default_scheduler,
            set_default_scheduler,
        )

        # Initially should be None
        assert get_default_scheduler() is None

        # Set a scheduler
        config = SchedulerConfig(enabled=True, interval=1)
        scheduler = SchedulerService(config=config)
        set_default_scheduler(scheduler)

        # Should now return the scheduler
        assert get_default_scheduler() is scheduler


# Additional integration tests that could be run with a real FastAPI app
@pytest.mark.skipif(
    not SCHEDULER_TESTS_ENABLED, reason="Schedule package not available"
)
class TestFastAPIIntegration:
    """Test integration with FastAPI applications."""

    async def test_middleware_creation(self):
        """Test creating scheduler middleware."""
        from jvspatial.api.integrations.scheduler.scheduler import (
            SchedulerConfig,
            SchedulerMiddleware,
            SchedulerService,
        )

        config = SchedulerConfig(enabled=True, interval=1)
        scheduler = SchedulerService(config=config)

        # This would normally be added to a FastAPI app
        middleware = SchedulerMiddleware(None, scheduler)  # None as app for testing
        assert middleware.scheduler_service is scheduler

    async def test_add_scheduler_to_app_function(self):
        """Test the add_scheduler_to_app function."""
        from jvspatial.api.integrations.scheduler.scheduler import (
            SchedulerConfig,
            SchedulerService,
            add_scheduler_to_app,
        )

        # Mock FastAPI app
        mock_app = Mock()
        mock_app.add_middleware = Mock()
        mock_app.on_event = Mock()

        config = SchedulerConfig(enabled=True, interval=1)
        scheduler = SchedulerService(config=config)

        add_scheduler_to_app(mock_app, scheduler)

        # Verify middleware was added
        mock_app.add_middleware.assert_called_once()

        # Verify event handlers were registered
        assert mock_app.on_event.call_count == 2  # startup and shutdown
