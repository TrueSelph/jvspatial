"""No-op deferred schedulers for unsupported providers or misconfiguration."""

import logging
import uuid
from typing import Any, Optional

from .base import RetryConfig, TaskScheduler

logger = logging.getLogger(__name__)


class LoggingNoopTaskScheduler(TaskScheduler):
    """Accept schedule calls but only log; returns a synthetic reference id."""

    def __init__(self, message: str = "Deferred task not dispatched") -> None:
        self._message = message

    def schedule(
        self,
        task_type: str,
        payload: Any,
        delay_seconds: int = 0,
        retry_config: Optional[RetryConfig] = None,
        run_at: Optional[float] = None,
    ) -> str:
        """Log and return a synthetic reference; see base class."""
        logger.warning("%s (task_type=%s)", self._message, task_type)
        return f"noop-{uuid.uuid4()}"
