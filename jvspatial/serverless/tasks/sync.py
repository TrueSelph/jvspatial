"""Synchronous fallback task scheduler."""

import uuid
from typing import Any, Callable, Optional

from .base import RetryConfig, TaskScheduler


class NoopOrSyncScheduler(TaskScheduler):
    """Fallback scheduler that executes handlers inline."""

    def __init__(self, executor: Optional[Callable[[str, Any], Any]] = None):
        self._executor = executor

    def schedule(
        self,
        task_type: str,
        payload: Any,
        delay_seconds: int = 0,
        retry_config: Optional[RetryConfig] = None,
        run_at: Optional[float] = None,
    ) -> str:
        """Run the configured executor immediately; see base class."""
        reference = f"sync-{uuid.uuid4()}"
        if self._executor is not None:
            # Strict-safe default: execute immediately in-process.
            self._executor(task_type, payload)
        return reference
