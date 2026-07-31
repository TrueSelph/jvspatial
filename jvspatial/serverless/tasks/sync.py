"""Synchronous fallback task scheduler."""

import uuid
from typing import Any, Callable, Optional

from jvspatial.exceptions import TaskSchedulerNotConfiguredError

from .base import RetryConfig, TaskScheduler


class NoopOrSyncScheduler(TaskScheduler):
    """Fallback scheduler that executes handlers inline, or drops them.

    With an ``executor`` this runs the task in-process, which satisfies
    ``strict``: the work happened before ``schedule`` returned. Without one
    — the shape :func:`~jvspatial.serverless.factory.get_task_scheduler`
    returns for every non-serverless caller — nothing runs at all, so a
    ``strict`` dispatch raises rather than handing back a reference for work
    that will never happen.
    """

    def __init__(self, executor: Optional[Callable[[str, Any], Any]] = None):
        self._executor = executor

    def schedule(
        self,
        task_type: str,
        payload: Any,
        delay_seconds: int = 0,
        retry_config: Optional[RetryConfig] = None,
        run_at: Optional[float] = None,
        strict: bool = False,
    ) -> str:
        """Run the configured executor immediately; see base class."""
        reference = f"sync-{uuid.uuid4()}"
        if self._executor is None:
            if strict:
                raise TaskSchedulerNotConfiguredError(
                    task_type,
                    "no executor is configured on NoopOrSyncScheduler, so the "
                    "task would be silently dropped; inject "
                    "config.task_scheduler or enable serverless mode",
                )
            return reference
        # Executed in-process, so the strict guarantee is already met.
        self._executor(task_type, payload)
        return reference
