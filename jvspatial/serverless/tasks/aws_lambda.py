"""AWS Lambda async invoke and EventBridge Scheduler for deferred tasks."""

import json
import logging
import re
import time
import uuid
from typing import Any, Dict, Optional

from jvspatial.env import env, parse_bool, resolve_aws_region
from jvspatial.exceptions import TaskDispatchError, TaskSchedulerNotConfiguredError
from jvspatial.runtime.eventbridge_readiness import resolve_eventbridge_lambda_arn

from .base import RetryConfig, TaskScheduler

logger = logging.getLogger(__name__)

# Hard ceiling on a single Lambda execution. A task deferred further out than
# this cannot be honored by invoking now and waiting inside the handler.
_LAMBDA_MAX_TIMEOUT_SECONDS = 900

_lambda_client_cache: list[Optional[Any]] = [None]
_scheduler_client_cache: list[Optional[Any]] = [None]


def _invoke_rejection(response: Any) -> Optional[str]:
    """Describe why an async ``invoke`` response is a failure, else ``None``.

    ``InvocationType="Event"`` returns ``202`` when Lambda has accepted the
    invocation. Anything else — or a ``FunctionError`` — means the task was
    not queued, even though boto3 did not raise.
    """
    if not isinstance(response, dict):
        return None
    function_error = response.get("FunctionError")
    if function_error:
        return f"Lambda returned FunctionError={function_error!r}"
    status = response.get("StatusCode")
    if status is None:
        return None
    try:
        status_int = int(status)
    except (TypeError, ValueError):
        return f"Lambda returned a non-numeric StatusCode={status!r}"
    if 200 <= status_int < 300:
        return None
    return f"Lambda returned StatusCode={status_int}"


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
    return env(
        "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED", default=False, parse=parse_bool
    )


def _eventbridge_role_arn() -> str:
    return env("JVSPATIAL_EVENTBRIDGE_ROLE_ARN", default="")


def _eventbridge_lambda_arn() -> str:
    class _EnvView:
        eventbridge_lambda_arn = env("JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN", default="")
        aws_lambda_function_name = env("AWS_LAMBDA_FUNCTION_NAME", default="")
        aws_region = resolve_aws_region()
        aws_account_id = env("AWS_ACCOUNT_ID", default="")

    return resolve_eventbridge_lambda_arn(_EnvView())


def _eventbridge_schedule_group() -> str:
    return env("JVSPATIAL_EVENTBRIDGE_SCHEDULER_GROUP", default="default") or "default"


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
    # Match the Lambda async-invoke body: a handler reads process_at to avoid
    # re-waiting its own batching window after EventBridge already fired at
    # run_at.
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
            function_name or env("AWS_LAMBDA_FUNCTION_NAME") or ""
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
        strict: bool = False,
    ) -> str:
        """Dispatch via Lambda async invoke or EventBridge Scheduler; see base class.

        Under ``strict=True`` every path that fails to hand the task to AWS
        raises instead of returning a synthetic reference. A caller that opted
        into strict has failure handling of its own — signalling an error back
        to an upstream sender, releasing a dedup claim so a retry is accepted
        — and a reference for a task that was never dispatched converts that
        handling into silent data loss.
        """
        reference = f"aws-lambda-{uuid.uuid4()}"
        if retry_config is not None:
            pass  # reserved for future retry metadata on envelope

        if not self._function_name:
            if strict:
                raise TaskSchedulerNotConfiguredError(
                    task_type, "AWS_LAMBDA_FUNCTION_NAME is not set"
                )
            logger.warning(
                "AWS_LAMBDA_FUNCTION_NAME not set; deferred task %s not dispatched",
                task_type,
            )
            return reference

        effective_run_at = run_at
        if effective_run_at is None and delay_seconds > 0:
            effective_run_at = time.time() + delay_seconds

        if effective_run_at is not None:
            if _create_eventbridge_schedule(
                task_type, payload, effective_run_at, reference
            ):
                return reference
            # EventBridge failed, so we fall back to invoking now with
            # ``process_at`` in the body and let the handler wait. That only
            # works inside a single Lambda execution: past the maximum
            # timeout the handler cannot survive until ``run_at``, so the
            # task is doomed and a strict caller must hear about it. Shorter
            # delays fall through to the invoke below, which strict guards.
            if strict and effective_run_at - time.time() > _LAMBDA_MAX_TIMEOUT_SECONDS:
                raise TaskDispatchError(
                    task_type,
                    "EventBridge scheduling failed and the requested delay "
                    f"exceeds the {_LAMBDA_MAX_TIMEOUT_SECONDS}s Lambda "
                    "timeout, so an immediate invoke cannot honor run_at",
                )

        body = _build_invoke_body(task_type, payload, effective_run_at)
        try:
            response = self._client().invoke(
                FunctionName=self._function_name,
                InvocationType="Event",
                Payload=json.dumps(body),
            )
        except Exception as e:
            logger.error(
                "Failed Lambda invoke for deferred task %s: %s",
                task_type,
                e,
                exc_info=True,
            )
            if strict:
                raise TaskDispatchError(
                    task_type, f"Lambda invoke raised {type(e).__name__}: {e}"
                ) from e
            return reference

        # A raised exception is not the only failure mode: an async invoke
        # answers 202 on acceptance, and a rejected or errored invocation
        # comes back as a non-2xx StatusCode or a FunctionError field.
        rejection = _invoke_rejection(response)
        if rejection is not None:
            logger.error("Lambda rejected deferred task %s: %s", task_type, rejection)
            if strict:
                raise TaskDispatchError(task_type, rejection)
            return reference

        logger.info("Invoked deferred task %s (ref=%s)", task_type, reference)
        return reference
