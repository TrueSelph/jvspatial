"""Optional scheduler integration for jvspatial.

This package provides lightweight, optional scheduling capabilities
integrated with FastAPI using the `schedule` library.

The scheduler system includes:
- SchedulerService: Core scheduler service with thread-based execution
- ScheduledTask: Pydantic models for task configuration and tracking
- Decorators: @scheduled and @walker_scheduled for easy task registration
- Middleware: FastAPI lifecycle integration
- Integration with FastAPI lifecycle management

Requires the `schedule` package to be installed.
Install with: pip install jvspatial[scheduler]
"""

import warnings
from typing import Any

# Handle optional schedule dependency
try:
    import schedule

    SCHEDULE_AVAILABLE = True
except ImportError:
    SCHEDULE_AVAILABLE = False
    schedule = None


def _require_schedule():
    """Helper function to check if schedule package is available."""
    if not SCHEDULE_AVAILABLE:
        raise ImportError(
            "The 'schedule' package is required for scheduler functionality. "
            "Install it with: pip install schedule>=1.2.0 or pip install jvspatial[scheduler]"
        )


# Define the missing dependency factory function
def _missing_dependency_factory(name: str):
    def _missing_class(*args: Any, **kwargs: Any) -> None:
        _require_schedule()

    _missing_class.__name__ = name
    return _missing_class


# Conditional imports
if SCHEDULE_AVAILABLE:
    from .decorators import (
        clear_scheduled_registry,
        get_default_scheduler,
        get_schedule_info,
        get_scheduled_tasks,
        is_scheduled,
        on_schedule,
        register_scheduled_tasks,
        set_default_scheduler,
    )
    from .entities import (
        ExecutionRecord,
        ScheduleConfig,
        ScheduledTask,
    )
    from .middleware import (
        SchedulerLifecycleManager,
        SchedulerMiddleware,
        add_scheduler_to_app,
    )
    from .scheduler import SchedulerConfig, SchedulerService

    # Make key classes and functions available at package level
    __all__ = [
        # Core scheduler classes
        "SchedulerService",
        "SchedulerConfig",
        "ScheduledTask",
        "ScheduleConfig",
        "ExecutionRecord",
        "TaskExecutionRecord",
        # Middleware classes and functions
        "SchedulerMiddleware",
        "SchedulerLifecycleManager",
        "add_scheduler_to_app",
        # Decorator functions
        "on_schedule",
        "set_default_scheduler",
        "get_default_scheduler",
        "register_scheduled_tasks",
        "get_scheduled_tasks",
        "clear_scheduled_registry",
        "is_scheduled",
        "get_schedule_info",
        # Availability flag
        "SCHEDULE_AVAILABLE",
        # Test utility
        "_missing_dependency_factory",
    ]
else:
    # Create placeholder classes that raise helpful errors
    SchedulerService = _missing_dependency_factory("SchedulerService")  # type: ignore[misc]
    SchedulerConfig = _missing_dependency_factory("SchedulerConfig")  # type: ignore[misc]
    ScheduledTask = _missing_dependency_factory("ScheduledTask")  # type: ignore[misc]
    ScheduleConfig = _missing_dependency_factory("ScheduleConfig")  # type: ignore[misc]
    ExecutionRecord = _missing_dependency_factory("ExecutionRecord")  # type: ignore[misc]

    # Middleware placeholders
    SchedulerMiddleware = _missing_dependency_factory("SchedulerMiddleware")  # type: ignore[misc]
    SchedulerLifecycleManager = _missing_dependency_factory("SchedulerLifecycleManager")  # type: ignore[misc]
    add_scheduler_to_app = _missing_dependency_factory("add_scheduler_to_app")  # type: ignore[misc]

    # Decorator placeholders
    on_schedule = _missing_dependency_factory("on_schedule")
    set_default_scheduler = _missing_dependency_factory("set_default_scheduler")
    get_default_scheduler = _missing_dependency_factory("get_default_scheduler")
    register_scheduled_tasks = _missing_dependency_factory("register_scheduled_tasks")
    get_scheduled_tasks = _missing_dependency_factory("get_scheduled_tasks")
    clear_scheduled_registry = _missing_dependency_factory("clear_scheduled_registry")
    is_scheduled = _missing_dependency_factory("is_scheduled")
    get_schedule_info = _missing_dependency_factory("get_schedule_info")

    __all__ = ["SCHEDULE_AVAILABLE", "_missing_dependency_factory"]

    # Issue a warning when the package is imported without the dependency
    warnings.warn(
        "The 'schedule' package is not installed. Scheduler functionality will not be available. "
        "Install it with: pip install schedule>=1.2.0 or pip install jvspatial[scheduler]",
        UserWarning,
        stacklevel=2,
    )


# Backward compatibility alias
SCHEDULER_AVAILABLE = SCHEDULE_AVAILABLE
