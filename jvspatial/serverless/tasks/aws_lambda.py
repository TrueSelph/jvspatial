"""AWS Lambda async invoke and EventBridge Scheduler for deferred tasks."""

import json
import logging
import re
import time
import uuid
from typing import Any, Dict, Optional

from jvspatial.env import load_env

from .base import RetryConfig, TaskScheduler

logger = logging.getLogger(__name__)

_lambda_client_cache: list[Optional[Any]] = [None]
_scheduler_client_cache: list[Optional[Any]] = [None]


def _get_lambda_client() -> Any:
    if _lambda_client_cache[0] is None:
        import boto3

        _lambda_client_cache[0] = boto3.client("lambda")
    return _lambda_client_cache[0]


def _get_scheduler_client() -> Any:
    if _scheduler_client_cache[0] is None:
        import boto3

        _scheduler_client_cache[0] = boto3.client("scheduler")
    return _scheduler_client_cache[0]


def _eventbridge_enabled() -> bool:
    return load_env().eventbridge_scheduler_enabled_raw.strip().lower() == "true"


def _eventbridge_role_arn() -> str:
    return load_env().eventbridge_role_arn


def _eventbridge_lambda_arn() -> str:
    e = load_env()
    arn = e.eventbridge_lambda_arn
    if arn:
        return arn
    func_name = e.aws_lambda_function_name.strip()
    if func_name:
        region = e.aws_region
        account = e.aws_account_id
        if account:
            return f"arn:aws:lambda:{region}:{account}:function:{func_name}"
    return ""


def _eventbridge_schedule_group() -> str:
    return load_env().eventbridge_scheduler_group


def _build_invoke_body(
    task_type: str, payload: Any, process_at: Optional[float]
) -> Dict[str, Any]:
    body: Dict[str, Any] = {"task_type": task_type}
    if isinstance(payload, dict):
        body.update(payload)
    else:
        body["payload"] = payload
    if process_at is not None:
        body["process_at"] = process_at
    return body


def _create_eventbridge_schedule(
    task_type: str,
    payload: Any,
    run_at: float,
    reference: str,
) -> bool:
    """One-shot EventBridge schedule at ``run_at``. Returns True on success."""
    from datetime import datetime, timezone

    if not _eventbridge_enabled():
        return False
    role_arn = _eventbridge_role_arn()
    lambda_arn = _eventbridge_lambda_arn()
    if not role_arn or not lambda_arn:
        return False

    if isinstance(payload, dict):
        bridge_input: Dict[str, Any] = {**payload, "task_type": task_type}
    else:
        bridge_input = {"task_type": task_type, "payload": payload}
    # Match Lambda async-invoke body: handlers (e.g. WhatsApp media_batch) use
    # process_at to avoid sleeping media_batch_window again after EventBridge
    # already fired at run_at.
    bridge_input["process_at"] = run_at

    try:
        client = _get_scheduler_client()
        safe_ref = re.sub(r"[^a-zA-Z0-9_-]", "_", reference)[:48]
        name = f"jvdef-{safe_ref}"
        at_time = datetime.fromtimestamp(run_at, tz=timezone.utc)
        schedule_expr = f"at({at_time.strftime('%Y-%m-%dT%H:%M:%S')})"
        client.create_schedule(
            Name=name,
            GroupName=_eventbridge_schedule_group(),
            ScheduleExpression=schedule_expr,
            ScheduleExpressionTimezone="UTC",
            FlexibleTimeWindow={"Mode": "OFF"},
            Target={
                "Arn": lambda_arn,
                "RoleArn": role_arn,
                "Input": json.dumps(bridge_input),
            },
            ActionAfterCompletion="DELETE",
        )
        logger.info(
            "Created EventBridge schedule for task %s at %s", task_type, schedule_expr
        )
        return True
    except Exception as e:
        logger.warning(
            "EventBridge schedule failed for %s, falling back to Lambda invoke: %s",
            task_type,
            e,
        )
        return False


class AwsLambdaDeferredTaskScheduler(TaskScheduler):
    """Fire-and-forget deferred work via Lambda async invoke or EventBridge Scheduler."""

    def __init__(
        self,
        function_name: Optional[str] = None,
        lambda_client: Any = None,
    ):
        self._function_name = (
            function_name or load_env().aws_lambda_function_name
        ).strip()
        self._lambda_client = lambda_client

    def _client(self) -> Any:
        return self._lambda_client or _get_lambda_client()

    def schedule(
        self,
        task_type: str,
        payload: Any,
        delay_seconds: int = 0,
        retry_config: Optional[RetryConfig] = None,
        run_at: Optional[float] = None,
    ) -> str:
        """Dispatch via Lambda async invoke or EventBridge Scheduler; see base class."""
        reference = f"aws-lambda-{uuid.uuid4()}"
        if retry_config is not None:
            pass  # reserved for future retry metadata on envelope

        if not self._function_name:
            logger.warning(
                "AWS_LAMBDA_FUNCTION_NAME not set; deferred task %s not dispatched",
                task_type,
            )
            return reference

        effective_run_at = run_at
        if effective_run_at is None and delay_seconds > 0:
            effective_run_at = time.time() + delay_seconds

        if effective_run_at is not None and _create_eventbridge_schedule(
            task_type, payload, effective_run_at, reference
        ):
            return reference

        body = _build_invoke_body(task_type, payload, effective_run_at)
        try:
            self._client().invoke(
                FunctionName=self._function_name,
                InvocationType="Event",
                Payload=json.dumps(body),
            )
            logger.info("Invoked deferred task %s (ref=%s)", task_type, reference)
        except Exception as e:
            logger.error(
                "Failed Lambda invoke for deferred task %s: %s",
                task_type,
                e,
                exc_info=True,
            )
        return reference
