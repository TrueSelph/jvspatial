"""AWS SQS-backed deferred task scheduler."""

import json
import time
import uuid
from typing import Any, Optional

from .base import RetryConfig, TaskScheduler

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
    ) -> str:
        """Enqueue a message on SQS with optional delay; see base class."""
        reference = f"aws-sqs-{uuid.uuid4()}"
        if not self._sqs_client or not self._queue_url:
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
        self._sqs_client.send_message(
            QueueUrl=self._queue_url,
            MessageBody=json.dumps(message),
            DelaySeconds=delay,
        )
        return reference
