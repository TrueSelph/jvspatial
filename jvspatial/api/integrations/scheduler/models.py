"""Entities for the scheduler system.

This module defines the minimal data models needed by the jvspatial scheduler.
These are lightweight Pydantic models for configuration and execution tracking.
"""

from datetime import datetime
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class SchedulerConfig(BaseModel):
    """Configuration for the scheduler system.

    Attributes:
        enabled: Whether the scheduler is enabled
        timezone: Timezone for scheduling (e.g., "UTC", "America/New_York")
        interval: Polling interval in seconds for checking scheduled tasks
        max_concurrent_tasks: Maximum number of tasks that can run concurrently
        task_timeout: Default timeout for tasks in seconds
        log_level: Logging level for scheduler operations
        persistence_enabled: Whether to store schedules in GraphContext
        auto_cleanup: Whether to automatically clean up completed task records
        max_task_history: Maximum number of task execution records to keep
    """

    enabled: bool = False
    timezone: str = "UTC"
    interval: float = 1.0  # Check every second by default
    max_concurrent_tasks: int = 10
    task_timeout: int = 3600  # 1 hour default timeout
    log_level: str = "info"
    persistence_enabled: bool = False
    auto_cleanup: bool = True
    max_task_history: int = 100


class ExecutionRecord(BaseModel):
    """Record of a task execution.

    Lightweight record for tracking task execution history.
    """

    execution_id: str = Field(
        default_factory=lambda: f"exec_{int(datetime.now().timestamp())}"
    )
    task_id: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    success: Optional[bool] = None
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    duration_seconds: Optional[float] = None


class ScheduleConfig(BaseModel):
    """Configuration for a scheduled task's timing and execution."""

    schedule_spec: str  # e.g., "every 10 minutes", "daily at 14:30"
    max_concurrent: int = 1
    timeout_seconds: Optional[int] = None
    retry_count: int = 0
    retry_delay_seconds: int = 60


class ScheduledTask(BaseModel):
    """Lightweight scheduled task definition.

    This is a simple data model for scheduled tasks, intentionally not
    a graph Node because scheduler tasks are runtime constructs.
    """

    task_id: str
    task_type: str  # "function", "async_function", "walker", "async_walker"
    schedule: ScheduleConfig
    enabled: bool = True
    description: Optional[str] = None

    # Function execution
    function_ref: Optional[Callable] = None

    # Walker execution
    walker_name: Optional[str] = None
    walker_args: Dict[str, Any] = Field(default_factory=dict)

    # Runtime tracking (updated by scheduler)
    last_execution: Optional[datetime] = None
    next_execution: Optional[datetime] = None
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    model_config = ConfigDict(arbitrary_types_allowed=True)  # Allow Callable type

    def get_success_rate(self) -> float:
        """Calculate success rate as a percentage."""
        if self.execution_count == 0:
            return 0.0
        return self.success_count / self.execution_count

    def record_execution(
        self, success: bool, execution_time: Optional[datetime] = None
    ) -> None:
        """Record an execution result."""
        self.execution_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        if execution_time:
            self.last_execution = execution_time


# Type alias for backwards compatibility
TaskExecutionRecord = ExecutionRecord
