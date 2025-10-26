"""Decorators for scheduling functions and walker executions.

This module provides intuitive decorators that allow developers to easily
schedule functions and walkers to run at specific intervals using the
scheduler service.
"""

import functools
import inspect
import logging
from typing import Any, Callable, Dict, Optional

from .models import ScheduleConfig, ScheduledTask
from .scheduler import SchedulerService

# Global registry to store scheduled functions and walkers
_scheduled_registry: Dict[str, Dict[str, Any]] = {}
_default_scheduler = None


def set_default_scheduler(scheduler: SchedulerService) -> None:
    """Set the default scheduler service for decorators.

    Args:
        scheduler: SchedulerService instance to use as default
    """
    global _default_scheduler
    _default_scheduler = scheduler


def get_default_scheduler() -> Optional[SchedulerService]:
    """Get the default scheduler service.

    Returns:
        Default SchedulerService instance or None if not set
    """
    return _default_scheduler


async def register_scheduled_tasks(scheduler: SchedulerService) -> None:
    """Register all decorated tasks with a scheduler service.

    This function should be called after creating a scheduler service
    to register all tasks that were decorated with @on_schedule.

    Args:
        scheduler: SchedulerService instance to register tasks with
    """
    logger = logging.getLogger(__name__)

    if not _scheduled_registry:
        logger.info("No scheduled tasks found to register")
        return

    registered_count = 0
    for task_id, task_info in _scheduled_registry.items():
        try:
            task = task_info["task"]
            await scheduler.register_task(task)
            registered_count += 1
            logger.debug(f"Registered scheduled task: {task_id}")
        except Exception as e:
            logger.error(f"Failed to register scheduled task {task_id}: {e}")

    logger.info(f"Registered {registered_count} scheduled tasks with scheduler")


def on_schedule(
    schedule: str,
    task_id: Optional[str] = None,
    enabled: bool = True,
    max_concurrent: int = 1,
    timeout_seconds: Optional[int] = None,
    retry_count: int = 0,
    description: Optional[str] = None,
    scheduler: Optional[SchedulerService] = None,
) -> Callable:
    """Decorator to schedule a function for periodic execution.

    This decorator marks a function to be scheduled for periodic execution
    using the schedule syntax (e.g., "every 5 minutes", "daily at 14:30").

    Args:
        schedule: Schedule specification string (e.g., "every 1 hour")
        task_id: Unique identifier for the task (defaults to function name)
        enabled: Whether the task should be enabled by default
        max_concurrent: Maximum concurrent executions allowed
        timeout_seconds: Timeout for task execution in seconds
        retry_count: Number of retries on failure
        description: Human-readable description of the task
        scheduler: Specific scheduler to use (defaults to global scheduler)

    Returns:
        Decorated function that can be executed normally or scheduled

    Example:
        @on_schedule("every 30 minutes", description="Clean up temp files")
        def cleanup_temp_files():
            # Implementation here
            pass

        @on_schedule("daily at 02:00", task_id="daily_backup")
        async def backup_database():
            # Async implementation here
            pass
    """

    def decorator(func: Callable) -> Callable:
        # Generate task ID if not provided
        actual_task_id = task_id or f"{func.__module__}.{func.__name__}"

        # Create schedule config
        schedule_config = ScheduleConfig(
            schedule_spec=schedule,
            max_concurrent=max_concurrent,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
        )

        # Determine task type based on function inspection
        is_async = inspect.iscoroutinefunction(func)
        task_type = "async_function" if is_async else "function"

        # Create scheduled task
        scheduled_task = ScheduledTask(
            task_id=actual_task_id,
            task_type=task_type,
            function_ref=func,
            schedule=schedule_config,
            enabled=enabled,
            description=description or f"Scheduled {task_type}: {func.__name__}",
        )

        # Store in registry for later registration
        _scheduled_registry[actual_task_id] = {
            "task": scheduled_task,
            "function": func,
            "decorator_info": {
                "schedule": schedule,
                "task_id": actual_task_id,
                "enabled": enabled,
                "max_concurrent": max_concurrent,
                "timeout_seconds": timeout_seconds,
                "retry_count": retry_count,
                "description": description,
            },
        }

        # Note: Immediate registration is not supported in decorators
        # Use register_scheduled_tasks() after scheduler creation

        # Add scheduling metadata to the function
        func._scheduled_task_id = actual_task_id  # type: ignore[attr-defined]
        func._scheduled_config = schedule_config  # type: ignore[attr-defined]
        func._is_scheduled = True  # type: ignore[attr-defined]

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        # Copy scheduling metadata to wrapper
        wrapper._scheduled_task_id = actual_task_id  # type: ignore[attr-defined]
        wrapper._scheduled_config = schedule_config  # type: ignore[attr-defined]
        wrapper._is_scheduled = True  # type: ignore[attr-defined]

        return wrapper

    return decorator


def get_scheduled_tasks() -> Dict[str, Dict[str, Any]]:
    """Get all registered scheduled tasks from decorators.

    Returns:
        Dictionary mapping task IDs to task information
    """
    return _scheduled_registry.copy()


def clear_scheduled_registry() -> None:
    """Clear the scheduled task registry.

    This is mainly useful for testing or when you want to reset
    the decorator state.
    """
    global _scheduled_registry
    _scheduled_registry.clear()


def is_scheduled(func: Callable) -> bool:
    """Check if a function has been decorated with a scheduling decorator.

    Args:
        func: Function to check

    Returns:
        True if function is scheduled, False otherwise
    """
    return getattr(func, "_is_scheduled", False)


def get_schedule_info(func: Callable) -> Optional[Dict[str, Any]]:
    """Get scheduling information for a decorated function.

    Args:
        func: Function to get schedule info for

    Returns:
        Dictionary with schedule information or None if not scheduled
    """
    if not is_scheduled(func):
        return None

    task_id = getattr(func, "_scheduled_task_id", None)
    if task_id and task_id in _scheduled_registry:
        decorator_info = _scheduled_registry[task_id]["decorator_info"]
        return decorator_info if isinstance(decorator_info, dict) else None

    return None
