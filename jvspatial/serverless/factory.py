"""Resolve a :class:`TaskScheduler` for the current serverless environment."""

from __future__ import annotations

import logging
from typing import Any, Optional

from jvspatial.env import env
from jvspatial.runtime.serverless import detect_serverless_provider, is_serverless_mode

from .tasks.aws_lambda import AwsLambdaDeferredTaskScheduler
from .tasks.aws_sqs import AwsSqsTaskScheduler
from .tasks.base import RetryConfig, TaskScheduler
from .tasks.stub import LoggingNoopTaskScheduler
from .tasks.sync import NoopOrSyncScheduler

logger = logging.getLogger(__name__)

_NOOP_DEFERRED_LOGGED = False


def _resolve_provider(config: Optional[Any]) -> str:
    raw = env("JVSPATIAL_DEFERRED_TASK_PROVIDER", default="").lower()
    if raw and raw != "auto":
        return raw
    if config is not None:
        v = getattr(config, "deferred_task_provider", None)
        if v:
            return str(v).strip().lower()
    return detect_serverless_provider()


def _make_sqs_scheduler(queue_url: str) -> TaskScheduler:
    try:
        import boto3
    except ImportError:
        logger.warning(
            "boto3 not installed; cannot create SQS deferred task scheduler "
            "(pip install jvspatial[lambda])"
        )
        return LoggingNoopTaskScheduler(
            "boto3 not installed; deferred tasks not dispatched"
        )
    return AwsSqsTaskScheduler(boto3.client("sqs"), queue_url)


def _aws_task_scheduler() -> TaskScheduler:
    transport = env("JVSPATIAL_AWS_DEFERRED_TRANSPORT", default="").lower()
    fn = env("AWS_LAMBDA_FUNCTION_NAME", default="")
    queue_url = env("JVSPATIAL_AWS_SQS_QUEUE_URL", default="")

    if transport == "sqs":
        if queue_url:
            return _make_sqs_scheduler(queue_url)
        logger.warning(
            "JVSPATIAL_AWS_DEFERRED_TRANSPORT=sqs but JVSPATIAL_AWS_SQS_QUEUE_URL is unset"
        )
        if fn:
            return AwsLambdaDeferredTaskScheduler()
        return LoggingNoopTaskScheduler(
            "AWS SQS queue URL missing; deferred task not dispatched"
        )

    if transport == "lambda_invoke":
        if fn:
            return AwsLambdaDeferredTaskScheduler()
        if queue_url:
            return _make_sqs_scheduler(queue_url)
        return LoggingNoopTaskScheduler(
            "lambda_invoke selected but AWS_LAMBDA_FUNCTION_NAME is unset"
        )

    if fn:
        return AwsLambdaDeferredTaskScheduler()
    if queue_url:
        return _make_sqs_scheduler(queue_url)
    return LoggingNoopTaskScheduler(
        "AWS serverless: set AWS_LAMBDA_FUNCTION_NAME or JVSPATIAL_AWS_SQS_QUEUE_URL "
        "for deferred tasks"
    )


def get_task_scheduler(
    config: Optional[Any] = None,
    *,
    override: Optional[TaskScheduler] = None,
) -> TaskScheduler:
    """Return the process-wide deferred task scheduler.

    Precedence:
        1. ``override`` when provided
        2. ``config.task_scheduler`` when set (duck-typed attribute)
        3. Non-serverless → :class:`NoopOrSyncScheduler` with no executor (no-op)
        4. Serverless → provider-specific implementation or :class:`LoggingNoopTaskScheduler`
    """
    if override is not None:
        return override
    if config is not None:
        injected = getattr(config, "task_scheduler", None)
        if injected is not None:
            return injected

    if not is_serverless_mode(config):
        return NoopOrSyncScheduler(None)

    provider = _resolve_provider(config)
    if provider == "aws":
        return _aws_task_scheduler()
    return LoggingNoopTaskScheduler(
        f"Serverless provider '{provider}' has no deferred task implementation yet"
    )


def _note_noop_in_serverless(sched: TaskScheduler, config: Optional[Any]) -> None:
    global _NOOP_DEFERRED_LOGGED
    if not isinstance(sched, LoggingNoopTaskScheduler):
        return
    if not is_serverless_mode(config):
        return
    if not _NOOP_DEFERRED_LOGGED:
        _NOOP_DEFERRED_LOGGED = True
        logger.error(
            "Deferred task scheduler is a logging no-op while serverless mode is on; "
            "tasks will not run. Configure AWS (Lambda/SQS), set "
            "JVSPATIAL_DEFERRED_TASK_PROVIDER=aws, or inject config.task_scheduler."
        )


def dispatch_deferred_task(
    task_type: str,
    payload: Any,
    *,
    config: Optional[Any] = None,
    override: Optional[TaskScheduler] = None,
    delay_seconds: int = 0,
    retry_config: Optional[RetryConfig] = None,
    run_at: Optional[float] = None,
    strict: bool = False,
) -> str:
    """Schedule a JSON-serializable deferred task; thin wrapper over :func:`get_task_scheduler`.

    Args:
        strict: If True and serverless mode is on but the resolved scheduler is
            :class:`LoggingNoopTaskScheduler`, raise ``RuntimeError`` instead of
            returning a synthetic reference.
    """
    sched = get_task_scheduler(config, override=override)
    if (
        strict
        and is_serverless_mode(config)
        and isinstance(sched, LoggingNoopTaskScheduler)
    ):
        raise RuntimeError(
            "Deferred task scheduler is a no-op in serverless mode; configure an AWS "
            "transport (Lambda/SQS), or inject config.task_scheduler."
        )
    _note_noop_in_serverless(sched, config)
    return sched.schedule(
        task_type,
        payload,
        delay_seconds=delay_seconds,
        retry_config=retry_config,
        run_at=run_at,
    )
