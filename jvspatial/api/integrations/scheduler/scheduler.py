"""Core scheduler service for jvspatial.

This module provides the main scheduler service that manages scheduled tasks
using the `schedule` package with a background thread execution model,
similar to the AgentPulse pattern.
"""

import asyncio
import inspect
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import schedule

from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Walker

from .models import (
    ExecutionRecord,
    ScheduledTask,
    SchedulerConfig,
    TaskExecutionRecord,
)

# Availability flag for the schedule package
SCHEDULE_AVAILABLE = True


class SchedulerService:
    """Main scheduler service managing scheduled tasks.

    This service follows the AgentPulse pattern with a background thread
    that continuously checks for and executes scheduled tasks using the
    `schedule` package.

    Features:
    - Background thread execution
    - Integration with GraphContext for database operations
    - Support for both sync and async functions
    - Walker execution support
    - Task timeout and error handling
    - Execution tracking and statistics
    """

    def __init__(
        self,
        config: Optional[SchedulerConfig] = None,
        graph_context: Optional[GraphContext] = None,
    ):
        """Initialize the scheduler service.

        Args:
            config: Scheduler configuration
            graph_context: GraphContext for database operations
        """
        self.config = config or SchedulerConfig()
        self.graph_context = graph_context
        self.logger = logging.getLogger(__name__)

        # Threading components (similar to AgentPulse)
        self._event: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._executor = ThreadPoolExecutor(
            max_workers=self.config.max_concurrent_tasks
        )

        # Task management
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running_tasks: Dict[str, Any] = {}
        self._task_execution_count = 0

        # Schedule instance
        self._schedule = schedule

        # Statistics
        self.start_time: Optional[datetime] = None
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0

    @property
    def is_running(self) -> bool:
        """Check if the scheduler is currently running."""
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._event is not None
            and not self._event.is_set()
        )

    def start(self, interval: Optional[float] = None) -> Optional[threading.Event]:
        """Start the scheduler in a background thread.

        Similar to AgentPulse.start() method.

        Args:
            interval: Time in seconds between each execution cycle

        Returns:
            threading.Event that can be set to stop the scheduler
        """
        if self.is_running:
            self.logger.info("Scheduler is already running")
            return self._event

        if interval is None:
            interval = self.config.interval

        self._event = threading.Event()
        self.start_time = datetime.utcnow()

        class SchedulerThread(threading.Thread):
            def __init__(self, scheduler_service: "SchedulerService"):
                super().__init__(daemon=True, name="jvspatial-scheduler")
                self.scheduler_service = scheduler_service

            def run(self) -> None:
                scheduler_service = self.scheduler_service
                while (
                    scheduler_service._event and not scheduler_service._event.is_set()
                ):
                    try:
                        scheduler_service._schedule.run_pending()
                        time.sleep(interval or 1.0)
                    except Exception as e:
                        scheduler_service.logger.error(
                            f"Error in scheduler thread: {e}"
                        )
                        time.sleep(interval or 1.0)  # Continue running despite errors

        self._thread = SchedulerThread(self)
        self._thread.start()

        self.logger.info(f"Scheduler started with {interval}s interval")
        return self._event

    def stop(self) -> None:
        """Stop the scheduler.

        Similar to AgentPulse.stop() method.
        """
        if self._event and not self._event.is_set():
            self.logger.info("Stopping scheduler...")
            self._event.set()

            if self._thread:
                self._thread.join(timeout=5.0)  # Wait up to 5 seconds

            # Cancel any running tasks
            for task_id, future in list(self._running_tasks.items()):
                if not future.done():
                    future.cancel()
                    self.logger.info(f"Cancelled running task: {task_id}")

            self._running_tasks.clear()
            self.logger.info("Scheduler stopped")

    async def register_task(self, task: ScheduledTask) -> None:
        """Register a scheduled task.

        Args:
            task: ScheduledTask object to register
        """
        # Store the task
        self._tasks[task.task_id] = task

        # Create schedule job based on task configuration
        job = self._create_schedule_job_from_task(task)

        if job:
            self.logger.info(
                f"Registered scheduled task: {task.task_id} ({task.schedule.schedule_spec})"
            )
        else:
            self.logger.error(
                f"Failed to register task: {task.task_id} - "
                f"invalid schedule: {task.schedule.schedule_spec}"
            )

    # Backwards compatibility method
    async def register_task_legacy(
        self, task_id: str, func: Callable, schedule_spec: str, **kwargs: Any
    ) -> None:
        """Legacy method for registering tasks (backwards compatibility)."""
        from .models import ScheduleConfig

        # Create ScheduledTask from legacy parameters
        schedule_config = ScheduleConfig(
            schedule_spec=schedule_spec,
            timeout_seconds=kwargs.get("timeout"),
            max_concurrent=kwargs.get("max_concurrent", 1),
            retry_count=kwargs.get("max_retries", 0),
        )

        # Determine task type
        import inspect

        if inspect.iscoroutinefunction(func):
            task_type = "async_function"
        elif inspect.isclass(func) and issubclass(func, Walker):
            task_type = "walker"
        else:
            task_type = "function"

        task = ScheduledTask(
            task_id=task_id,
            task_type=task_type,
            schedule=schedule_config,
            function_ref=func if task_type.endswith("function") else None,
            walker_name=(
                getattr(func, "__name__", None) if task_type == "walker" else None
            ),
            enabled=kwargs.get("enabled", True),
            description=kwargs.get("description"),
        )

        await self.register_task(task)

    def unregister_task(self, task_id: str) -> bool:
        """Unregister a scheduled task.

        Args:
            task_id: Task identifier to remove

        Returns:
            True if task was removed, False if not found
        """
        # Check if task exists
        if task_id not in self._tasks:
            return False

        # Remove from tasks dict
        del self._tasks[task_id]

        # Remove from schedule - this is tricky with the schedule library
        # We need to remove jobs that match our task
        jobs_to_remove = []
        for job in self._schedule.jobs:
            if hasattr(job.job_func, "__name__") and job.job_func.__name__.endswith(
                f"_wrapper_{task_id}"
            ):
                jobs_to_remove.append(job)

        for job in jobs_to_remove:
            self._schedule.cancel_job(job)

        self.logger.info(f"Unregistered scheduled task: {task_id}")
        return True

    def list_tasks(self) -> List[ScheduledTask]:
        """Get list of all registered tasks.

        Returns:
            List of ScheduledTask objects
        """
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a specific task by ID.

        Args:
            task_id: Task identifier

        Returns:
            ScheduledTask or None if not found
        """
        return self._tasks.get(task_id)

    def enable_task(self, task_id: str) -> bool:
        """Enable a scheduled task.

        Args:
            task_id: Task identifier

        Returns:
            True if task was enabled, False if not found
        """
        task = self._tasks.get(task_id)
        if task:
            task.enabled = True
            return True
        return False

    def disable_task(self, task_id: str) -> bool:
        """Disable a scheduled task.

        Args:
            task_id: Task identifier

        Returns:
            True if task was disabled, False if not found
        """
        task = self._tasks.get(task_id)
        if task:
            task.enabled = False
            return True
        return False

    def _create_schedule_job_from_task(
        self, task: ScheduledTask
    ) -> Optional[schedule.Job]:
        """Create a schedule job from a ScheduledTask object.

        Args:
            task: ScheduledTask to create job for

        Returns:
            Created schedule job or None if invalid
        """
        try:
            # Create wrapper function based on task type
            if task.task_type in ["function", "async_function"]:
                # func variable was unused, removing assignment
                pass
            elif task.task_type in ["walker", "async_walker"]:
                # For walkers, we create a function that executes the walker
                def walker_func():
                    # This would be the walker execution logic
                    # For now, we'll log it
                    self.logger.info(f"Executing walker: {task.walker_name}")

                # func variable was unused, removing assignment
                pass
            else:
                self.logger.error(f"Unknown task type: {task.task_type}")
                return None

            # Create wrapper function that handles execution
            def task_wrapper():
                self._execute_task_from_object(task)

            # Set a unique name for the wrapper to help with job removal
            task_wrapper.__name__ = f"task_wrapper_{task.task_id}"

            # Parse the schedule specification
            job = self._parse_schedule_spec(task.schedule.schedule_spec, task_wrapper)

            return job

        except Exception as e:
            self.logger.error(f"Error creating schedule job for {task.task_id}: {e}")
            return None

    def _create_schedule_job(
        self, schedule_spec: str, task_id: str, func: Callable, **kwargs: Any
    ) -> Optional[schedule.Job]:
        """Create a schedule job from specification.

        Args:
            schedule_spec: Schedule specification string
            task_id: Task identifier
            func: Function to execute
            **kwargs: Additional configuration

        Returns:
            Created schedule job or None if invalid spec
        """
        try:
            # Create wrapper function that handles execution
            def task_wrapper():
                self._execute_task(task_id, func, **kwargs)

            # Set a unique name for the wrapper to help with job removal
            task_wrapper.__name__ = f"task_wrapper_{task_id}"

            # Parse the schedule specification
            job = self._parse_schedule_spec(schedule_spec, task_wrapper)

            return job

        except Exception as e:
            self.logger.error(f"Error creating schedule job for {task_id}: {e}")
            return None

    def _parse_schedule_spec(self, spec: str, func: Callable) -> Optional[schedule.Job]:
        """Parse schedule specification string into a schedule job.

        Supports formats like:
        - "every 10 seconds"
        - "every 5 minutes"
        - "every hour"
        - "every day"
        - "every day at 10:30"
        - "every monday"
        - "every wednesday at 13:15"
        - "every 5 to 10 minutes"

        Args:
            spec: Schedule specification string
            func: Function to schedule

        Returns:
            Schedule job or None if parsing failed
        """
        spec = spec.lower().strip()

        try:
            if spec.startswith("every "):
                spec = spec[6:]  # Remove "every "

                # Handle "X to Y minutes/seconds/hours" format
                if " to " in spec:
                    parts = spec.split(" to ")
                    if len(parts) == 2:
                        start_num = int(parts[0])
                        end_part = parts[1].split()
                        end_num = int(end_part[0])
                        unit = end_part[1] if len(end_part) > 1 else "minutes"

                        if unit.startswith("minute"):
                            return (
                                self._schedule.every(start_num)
                                .to(end_num)
                                .minutes.do(func)
                            )
                        elif unit.startswith("second"):
                            return (
                                self._schedule.every(start_num)
                                .to(end_num)
                                .seconds.do(func)
                            )
                        elif unit.startswith("hour"):
                            return (
                                self._schedule.every(start_num)
                                .to(end_num)
                                .hours.do(func)
                            )

                # Handle specific time formats
                if " at " in spec:
                    parts = spec.split(" at ", 1)
                    time_spec = parts[1]
                    day_spec = parts[0].strip()

                    if day_spec == "day":
                        return self._schedule.every().day.at(time_spec).do(func)
                    elif day_spec == "monday":
                        return self._schedule.every().monday.at(time_spec).do(func)
                    elif day_spec == "tuesday":
                        return self._schedule.every().tuesday.at(time_spec).do(func)
                    elif day_spec == "wednesday":
                        return self._schedule.every().wednesday.at(time_spec).do(func)
                    elif day_spec == "thursday":
                        return self._schedule.every().thursday.at(time_spec).do(func)
                    elif day_spec == "friday":
                        return self._schedule.every().friday.at(time_spec).do(func)
                    elif day_spec == "saturday":
                        return self._schedule.every().saturday.at(time_spec).do(func)
                    elif day_spec == "sunday":
                        return self._schedule.every().sunday.at(time_spec).do(func)

                # Handle numbered intervals
                parts = spec.split()
                if len(parts) >= 2 and parts[0].isdigit():
                    num = int(parts[0])
                    unit = parts[1]

                    if unit.startswith("second"):
                        return self._schedule.every(num).seconds.do(func)
                    elif unit.startswith("minute"):
                        return self._schedule.every(num).minutes.do(func)
                    elif unit.startswith("hour"):
                        return self._schedule.every(num).hours.do(func)
                    elif unit.startswith("day"):
                        return self._schedule.every(num).days.do(func)
                    elif unit.startswith("week"):
                        return self._schedule.every(num).weeks.do(func)

                # Handle simple units
                if spec == "second":
                    return self._schedule.every().second.do(func)
                elif spec == "minute":
                    return self._schedule.every().minute.do(func)
                elif spec == "hour":
                    return self._schedule.every().hour.do(func)
                elif spec == "day":
                    return self._schedule.every().day.do(func)
                elif spec == "week":
                    return self._schedule.every().week.do(func)
                elif spec == "monday":
                    return self._schedule.every().monday.do(func)
                elif spec == "tuesday":
                    return self._schedule.every().tuesday.do(func)
                elif spec == "wednesday":
                    return self._schedule.every().wednesday.do(func)
                elif spec == "thursday":
                    return self._schedule.every().thursday.do(func)
                elif spec == "friday":
                    return self._schedule.every().friday.do(func)
                elif spec == "saturday":
                    return self._schedule.every().saturday.do(func)
                elif spec == "sunday":
                    return self._schedule.every().sunday.do(func)

        except Exception as e:
            self.logger.error(f"Error parsing schedule spec '{spec}': {e}")

        return None

    def _execute_task_from_object(self, task: ScheduledTask) -> None:
        """Execute a scheduled task from ScheduledTask object.

        Args:
            task: ScheduledTask to execute
        """
        # Check if task is enabled
        if not task.enabled:
            return

        # Check if task is already running (basic concurrency control)
        if task.task_id in self._running_tasks:
            max_concurrent = task.schedule.max_concurrent
            if max_concurrent <= 1:
                self.logger.warning(
                    f"Task {task.task_id} is already running, skipping execution"
                )
                return

        # Create execution record
        execution_record = ExecutionRecord(task_id=task.task_id)
        timeout = task.schedule.timeout_seconds or self.config.task_timeout

        try:
            # Submit task to thread pool
            future = self._executor.submit(
                self._run_task_with_timeout,
                task.function_ref or (lambda: None),
                task.task_id,
                timeout,
            )
            self._running_tasks[task.task_id] = future

            self.logger.debug(f"Started execution of task: {task.task_id}")

        except Exception as e:
            self.logger.error(f"Failed to submit task {task.task_id}: {e}")
            execution_record.success = False
            execution_record.error_message = str(e)
            execution_record.completed_at = datetime.utcnow()
            self._update_execution_stats(execution_record)

    def _execute_task(self, task_id: str, func: Callable, **kwargs: Any) -> None:
        """Execute a scheduled task (legacy method).

        Args:
            task_id: Task identifier
            func: Function to execute
            **kwargs: Task configuration
        """
        # Try to find task in new system first
        task = self._tasks.get(task_id)
        if task:
            self._execute_task_from_object(task)
            return

        # Fallback to legacy execution (shouldn't happen with new system)
        self.logger.warning(f"Using legacy execution for task {task_id}")

        # Check if task is already running
        if task_id in self._running_tasks:
            self.logger.warning(
                f"Task {task_id} is already running, skipping execution"
            )
            return

        # Create execution record
        execution_record = ExecutionRecord(task_id=task_id)
        timeout = kwargs.get("timeout", self.config.task_timeout)

        try:
            # Submit task to thread pool
            future = self._executor.submit(
                self._run_task_with_timeout, func, task_id, timeout
            )
            self._running_tasks[task_id] = future

            self.logger.debug(f"Started execution of task: {task_id}")

        except Exception as e:
            self.logger.error(f"Failed to submit task {task_id}: {e}")
            execution_record.success = False
            execution_record.error_message = str(e)
            execution_record.completed_at = datetime.utcnow()
            self._update_execution_stats(execution_record)

    def _run_task_with_timeout(
        self, func: Callable, task_id: str, timeout: int
    ) -> None:
        """Run a task with timeout handling.

        Args:
            func: Function to execute
            task_id: Task identifier
            timeout: Timeout in seconds
        """
        execution_record = TaskExecutionRecord(task_id=task_id)

        try:
            if inspect.iscoroutinefunction(func):
                # Handle async functions
                result = self._run_async_task(func, timeout)
            elif inspect.isclass(func) and issubclass(func, Walker):
                # Handle Walker classes
                result = self._run_walker_task(func, timeout)
            else:
                # Handle sync functions
                result = func()

            execution_record.success = True
            execution_record.result = {"status": "completed"}
            if result is not None:
                execution_record.result["return_value"] = result

            self.logger.info(f"Task {task_id} completed successfully")

        except FutureTimeoutError:
            execution_record.success = False
            execution_record.error_message = f"Task timed out after {timeout} seconds"
            self.logger.error(f"Task {task_id} timed out")

        except Exception as e:
            execution_record.success = False
            execution_record.error_message = str(e)
            self.logger.error(f"Task {task_id} failed: {e}")

        finally:
            execution_record.completed_at = datetime.utcnow()
            if execution_record.started_at and execution_record.completed_at:
                duration = execution_record.completed_at - execution_record.started_at
                execution_record.duration_seconds = duration.total_seconds()

            self._update_execution_stats(execution_record)

            # Remove from running tasks
            self._running_tasks.pop(task_id, None)

    def _run_async_task(self, func: Callable, timeout: int) -> Any:
        """Run an async function.

        Args:
            func: Async function to execute
            timeout: Timeout in seconds

        Returns:
            Function result
        """
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Run with timeout
            return loop.run_until_complete(asyncio.wait_for(func(), timeout=timeout))
        finally:
            loop.close()

    def _run_walker_task(self, walker_class: type, timeout: int) -> Any:
        """Run a Walker class.

        Args:
            walker_class: Walker class to execute
            timeout: Timeout in seconds

        Returns:
            Walker execution result
        """
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def run_walker():
                if self.graph_context:
                    async with self.graph_context:
                        walker = walker_class()
                        return await walker.spawn()
                else:
                    walker = walker_class()
                    return await walker.spawn()

            # Run with timeout
            result_walker = loop.run_until_complete(
                asyncio.wait_for(run_walker(), timeout=timeout)
            )

            # Return the report as the result
            if hasattr(result_walker, "get_report"):
                return {"walker_report": result_walker.get_report()}
            else:
                return {"walker_id": result_walker.id}

        finally:
            loop.close()

    def _update_execution_stats(self, execution_record: TaskExecutionRecord) -> None:
        """Update execution statistics.

        Args:
            execution_record: Completed execution record
        """
        self.total_executions += 1
        if execution_record.success:
            self.successful_executions += 1
        else:
            self.failed_executions += 1

    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status and statistics.

        Returns:
            Status information dictionary
        """
        uptime_seconds: float = 0.0
        if self.start_time:
            uptime_seconds = (datetime.utcnow() - self.start_time).total_seconds()

        return {
            "is_running": self.is_running,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_seconds": uptime_seconds,
            "registered_tasks": len(self._tasks),
            "enabled_tasks": len(
                [task for task in self._tasks.values() if task.enabled]
            ),
            "running_tasks": len(self._running_tasks),
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": (
                self.successful_executions / self.total_executions
                if self.total_executions > 0
                else 0.0
            ),
            "scheduled_jobs": len(self._schedule.jobs),
            "config": self.config.model_dump(),
        }

    def get_task_list(self) -> List[Dict[str, Any]]:
        """Get list of all registered tasks with their status.

        Returns:
            List of task information dictionaries
        """
        tasks = []
        for task_id, task in self._tasks.items():
            task_info = {
                "task_id": task_id,
                "enabled": task.enabled,
                "schedule_spec": task.schedule.schedule_spec,
                "function_name": getattr(
                    task.function_ref, "__name__", task.walker_name or "unknown"
                ),
                "is_running": task_id in self._running_tasks,
                "timeout": task.schedule.timeout_seconds or self.config.task_timeout,
                "timezone": "UTC",  # Default timezone from config
            }
            tasks.append(task_info)

        return tasks


# ============================================================================
# Decorator and Registry Functions
# ============================================================================

# Global registry for scheduled tasks
_scheduled_tasks: Dict[str, Dict[str, Any]] = {}


def on_schedule(
    schedule_spec: str, task_id: Optional[str] = None, description: Optional[str] = None
):
    """Decorator to mark functions as scheduled tasks.

    Args:
        schedule_spec: Schedule specification (e.g., "every 10 seconds")
        task_id: Optional task ID (defaults to function name)
        description: Optional task description
    """

    def decorator(func: Callable) -> Callable:
        task_id_final = task_id or func.__name__

        # Store task metadata
        _scheduled_tasks[task_id_final] = {
            "function": func,
            "schedule": schedule_spec,
            "description": description or f"Scheduled task: {func.__name__}",
            "task_id": task_id_final,
        }

        # Mark function as scheduled
        func._is_scheduled = True  # type: ignore[attr-defined]
        func._schedule_info = {  # type: ignore[attr-defined]
            "schedule": schedule_spec,
            "description": description,
            "task_id": task_id_final,
        }

        return func

    return decorator


def is_scheduled(func: Callable) -> bool:
    """Check if a function is marked as scheduled.

    Args:
        func: Function to check

    Returns:
        True if function is scheduled
    """
    return hasattr(func, "_is_scheduled") and func._is_scheduled


def get_schedule_info(func: Callable) -> Optional[Dict[str, Any]]:
    """Get schedule information for a function.

    Args:
        func: Function to get info for

    Returns:
        Schedule info dict or None
    """
    return getattr(func, "_schedule_info", None)


def get_scheduled_tasks() -> Dict[str, Dict[str, Any]]:
    """Get all registered scheduled tasks.

    Returns:
        Dictionary of task_id -> task_info
    """
    return _scheduled_tasks.copy()


def clear_scheduled_registry() -> None:
    """Clear the scheduled tasks registry."""
    global _scheduled_tasks
    _scheduled_tasks.clear()


def register_scheduled_tasks(scheduler_service: SchedulerService) -> None:
    """Register all decorated tasks with a scheduler service.

    Args:
        scheduler_service: SchedulerService instance
    """
    for task_id, task_info in _scheduled_tasks.items():
        from .models import ScheduleConfig

        schedule_config = ScheduleConfig(
            schedule_spec=task_info["schedule"],
            timeout_seconds=30,  # Default timeout
            max_concurrent=1,
            retry_count=0,
        )

        task = ScheduledTask(
            task_id=task_id,
            task_type="function",
            schedule=schedule_config,
            function_ref=task_info["function"],
            enabled=True,
            description=task_info["description"],
        )

        # Register with scheduler (this should be sync)
        scheduler_service._tasks[task_id] = task


# ============================================================================
# Default Scheduler Management
# ============================================================================

_default_scheduler: Optional[SchedulerService] = None


def get_default_scheduler() -> Optional[SchedulerService]:
    """Get the default scheduler instance.

    Returns:
        Default SchedulerService or None
    """
    return _default_scheduler


def set_default_scheduler(scheduler: SchedulerService) -> None:
    """Set the default scheduler instance.

    Args:
        scheduler: SchedulerService instance
    """
    global _default_scheduler
    _default_scheduler = scheduler


# ============================================================================
# Middleware and FastAPI Integration
# ============================================================================


class SchedulerMiddleware:
    """Middleware for integrating scheduler with FastAPI."""

    def __init__(self, app, scheduler_service: SchedulerService):
        """Initialize middleware.

        Args:
            app: FastAPI app instance
            scheduler_service: SchedulerService instance
        """
        self.app = app
        self.scheduler_service = scheduler_service


class SchedulerLifecycleManager:
    """Lifecycle manager for scheduler integration."""

    def __init__(self, scheduler_service: SchedulerService):
        """Initialize lifecycle manager.

        Args:
            scheduler_service: SchedulerService instance
        """
        self.scheduler_service = scheduler_service
        self._is_started = False

    @property
    def is_started(self) -> bool:
        """Check if lifecycle manager is started."""
        return self._is_started

    async def start(self) -> None:
        """Start the scheduler lifecycle."""
        if not self._is_started:
            self.scheduler_service.start()
            self._is_started = True

    async def stop(self) -> None:
        """Stop the scheduler lifecycle."""
        if self._is_started:
            self.scheduler_service.stop()
            self._is_started = False


def add_scheduler_to_app(app, scheduler_service: SchedulerService) -> None:
    """Add scheduler to FastAPI app.

    Args:
        app: FastAPI app instance
        scheduler_service: SchedulerService instance
    """
    # Add middleware
    app.add_middleware(SchedulerMiddleware, scheduler_service=scheduler_service)

    # Add startup/shutdown events
    @app.on_event("startup")
    async def startup_scheduler():
        scheduler_service.start()

    @app.on_event("shutdown")
    async def shutdown_scheduler():
        scheduler_service.stop()


# ============================================================================
# Error Handling for Missing Dependencies
# ============================================================================


def _missing_dependency_factory(class_name: str):
    """Factory for creating error classes when dependencies are missing."""

    class MissingDependencyError(ImportError):
        def __init__(self):
            super().__init__(
                f"{class_name} requires the schedule package. Install it with: pip install schedule"
            )

    # Return a class that raises ImportError when instantiated
    class ErrorClass:
        def __init__(self):
            raise MissingDependencyError()

    return ErrorClass
