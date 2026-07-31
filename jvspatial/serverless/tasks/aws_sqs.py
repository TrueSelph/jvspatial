"""AWS SQS-backed deferred task scheduler."""

import json
import logging
import time
import uuid
from typing import Any, Optional

from jvspatial.exceptions import TaskDispatchError, TaskSchedulerNotConfiguredError

from .base import RetryConfig, TaskScheduler

logger = logging.getLogger(__name__)

# SQS maximum per-message delay
_SQS_MAX_DELAY_SECONDS = 900


class AwsSqsTaskScheduler(TaskScheduler):
    """Send deferred tasks to SQS with optional delay.

    Pass a boto3 SQS client and queue URL, typically from configuration or DI.
    """

    def __init__(self, sqs_client: Any = None, queue_url: Optional[str] = None):
        self._sqs_client = sqs_client
        self._queue_url = queue_url

    def schedule(
        self,
        task_type: str,
        payload: Any,
        delay_seconds: int = 0,
        retry_config: Optional[RetryConfig] = None,
        run_at: Optional[float] = None,
        strict: bool = False,
    ) -> str:
        """Enqueue a message on SQS with optional delay; see base class.

        ``strict`` is the single switch that decides whether a failed dispatch
        raises, on every transport. Previously ``send_message`` failures
        propagated here while the Lambda transport swallowed them, so the same
        application code had opposite failure semantics depending on
        ``JVSPATIAL_AWS_DEFERRED_TRANSPORT``.
        """
        reference = f"aws-sqs-{uuid.uuid4()}"
        if not self._sqs_client or not self._queue_url:
            if strict:
                raise TaskSchedulerNotConfiguredError(
                    task_type, "SQS client or queue URL is not configured"
                )
            return reference

        delay = max(0, int(delay_seconds))
        if run_at is not None:
            delay = max(0, int(run_at - time.time()))
        delay = min(delay, _SQS_MAX_DELAY_SECONDS)

        message = {
            "task_type": task_type,
            "payload": payload,
            "retry": retry_config.__dict__ if retry_config else None,
            "reference": reference,
            "run_at": run_at,
        }
        try:
            self._sqs_client.send_message(
                QueueUrl=self._queue_url,
                MessageBody=json.dumps(message),
                DelaySeconds=delay,
            )
        except Exception as e:
            logger.error(
                "Failed SQS send_message for deferred task %s: %s",
                task_type,
                e,
                exc_info=True,
            )
            if strict:
                raise TaskDispatchError(
                    task_type, f"SQS send_message raised {type(e).__name__}: {e}"
                ) from e
        return reference
