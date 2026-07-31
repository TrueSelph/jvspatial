"""No-op deferred schedulers for unsupported providers or misconfiguration."""

import logging
import uuid
from typing import Any, Optional

from jvspatial.exceptions import TaskSchedulerNotConfiguredError

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
        strict: bool = False,
    ) -> str:
        """Log and return a synthetic reference; see base class.

        Downgraded to DEBUG so a misconfigured serverless deployment does
        not flood CloudWatch with one WARNING per dispatch. The
        once-per-process startup error from
        ``serverless.factory._note_noop_in_serverless`` is sufficient
        (audit §7.14 / SPEC §11.2).

        ``dispatch_deferred_task`` guards the same condition earlier and with
        more context, so this raise is the backstop for direct callers and
        for a no-op injected via ``config.task_scheduler`` outside serverless
        mode — where the factory's ``is_serverless_mode`` gate does not fire.
        """
        if strict:
            raise TaskSchedulerNotConfiguredError(task_type, self._message)
        logger.debug("%s (task_type=%s)", self._message, task_type)
        return f"noop-{uuid.uuid4()}"
