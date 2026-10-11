"""Tests for AwsLambdaDeferredTaskScheduler."""

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from jvspatial.exceptions import TaskDispatchError, TaskSchedulerNotConfiguredError
from jvspatial.runtime.serverless import reset_serverless_mode_cache
from jvspatial.serverless.tasks.aws_lambda import AwsLambdaDeferredTaskScheduler

try:  # botocore ships with boto3; fall back so the suite runs without it.
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover - exercised only without boto3

    class ClientError(Exception):  # type: ignore[no-redef]
        def __init__(self, error_response, operation_name):
            super().__init__(f"{operation_name}: {error_response}")


@pytest.fixture(autouse=True)
def _clear_serverless_caches():
    reset_serverless_mode_cache()
    yield
    reset_serverless_mode_cache()


def test_schedule_lambda_invoke_payload_merges_dict():
    mock_client = MagicMock()
    sched = AwsLambdaDeferredTaskScheduler(
        function_name="fn",
        lambda_client=mock_client,
    )
    sched.schedule(
        "app.media.batch",
        {"sender": "u1", "batch_window": 1.5},
        run_at=12345.0,
    )
    mock_client.invoke.assert_called_once()
    call_kw = mock_client.invoke.call_args.kwargs
    assert call_kw["FunctionName"] == "fn"
    assert call_kw["InvocationType"] == "Event"
    body = json.loads(call_kw["Payload"])
    assert body["task_type"] == "app.media.batch"
    assert body["sender"] == "u1"
    assert body["batch_window"] == 1.5
    assert body["process_at"] == 12345.0


def test_schedule_prefers_eventbridge_when_enabled():
    future = time.time() + 3600
    mock_sched_client = MagicMock()
    mock_lambda = MagicMock()
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED": "true",
            "JVSPATIAL_EVENTBRIDGE_ROLE_ARN": "arn:aws:iam::1:role/r",
            "JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN": "arn:aws:lambda:us-east-1:1:function:f",
        },
        clear=False,
    ):
        with patch(
            "jvspatial.serverless.tasks.aws_lambda._get_scheduler_client",
            return_value=mock_sched_client,
        ):
            sched = AwsLambdaDeferredTaskScheduler(
                function_name="f",
                lambda_client=mock_lambda,
            )
            sched.schedule("task.x", {"k": "v"}, run_at=future)
    mock_sched_client.create_schedule.assert_called_once()
    mock_lambda.invoke.assert_not_called()
    input_body = json.loads(
        mock_sched_client.create_schedule.call_args.kwargs["Target"]["Input"]
    )
    assert input_body["task_type"] == "task.x"
    assert input_body["k"] == "v"
    assert input_body["process_at"] == future


def test_delay_seconds_becomes_process_at_in_payload():
    mock_client = MagicMock()
    sched = AwsLambdaDeferredTaskScheduler(
        function_name="fn",
        lambda_client=mock_client,
    )
    with patch("jvspatial.serverless.tasks.aws_lambda.time.time", return_value=1000.0):
        with patch(
            "jvspatial.serverless.tasks.aws_lambda._create_eventbridge_schedule",
            return_value=False,
        ):
            sched.schedule("t", {"x": 1}, delay_seconds=30)
    body = json.loads(mock_client.invoke.call_args.kwargs["Payload"])
    assert body["process_at"] == 1030.0


# ── strict semantics ────────────────────────────────────────────────────────
#
# strict=True is the caller stating that it has its own failure handling —
# signalling an error back to an upstream sender, releasing a dedup claim so a
# retry is accepted — and that an undispatched task must therefore RAISE
# rather than hand back a synthetic reference. Returning a reference for work
# that was never dispatched turns that handling into silent data loss.


def test_strict_raises_when_function_name_unset(monkeypatch):
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    sched = AwsLambdaDeferredTaskScheduler(function_name="")
    with pytest.raises(
        TaskSchedulerNotConfiguredError, match="AWS_LAMBDA_FUNCTION_NAME"
    ):
        sched.schedule("t.task", {"k": "v"}, strict=True)


def test_non_strict_keeps_fire_and_forget_when_function_name_unset(monkeypatch):
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    sched = AwsLambdaDeferredTaskScheduler(function_name="")
    ref = sched.schedule("t.task", {"k": "v"})
    assert ref.startswith("aws-lambda-")


def test_strict_raises_task_dispatch_error_on_invoke_failure():
    client = MagicMock()
    client.invoke.side_effect = ClientError(
        {"Error": {"Code": "ServiceException", "Message": "boom"}}, "Invoke"
    )
    sched = AwsLambdaDeferredTaskScheduler(function_name="fn", lambda_client=client)
    with pytest.raises(TaskDispatchError) as excinfo:
        sched.schedule("t.task", {"k": "v"}, strict=True)
    assert excinfo.value.task_type == "t.task"
    # Still a RuntimeError, so pre-existing handlers keep working.
    assert isinstance(excinfo.value, RuntimeError)


def test_non_strict_swallows_invoke_failure_unchanged():
    client = MagicMock()
    client.invoke.side_effect = ClientError(
        {"Error": {"Code": "ServiceException", "Message": "boom"}}, "Invoke"
    )
    sched = AwsLambdaDeferredTaskScheduler(function_name="fn", lambda_client=client)
    ref = sched.schedule("t.task", {"k": "v"})
    assert ref.startswith("aws-lambda-")


def test_strict_success_returns_reference():
    client = MagicMock()
    client.invoke.return_value = {"StatusCode": 202}
    sched = AwsLambdaDeferredTaskScheduler(function_name="fn", lambda_client=client)
    ref = sched.schedule("t.task", {"k": "v"}, strict=True)
    assert ref.startswith("aws-lambda-")
    client.invoke.assert_called_once()


# ── invoke responses that do not raise but are still failures ───────────────


@pytest.mark.parametrize(
    "response",
    [
        {"StatusCode": 500},
        {"StatusCode": 202, "FunctionError": "Unhandled"},
        {"StatusCode": "not-a-number"},
    ],
)
def test_strict_raises_on_rejected_invoke_response(response):
    """boto3 returns rather than raising when Lambda rejects the invocation."""
    client = MagicMock()
    client.invoke.return_value = response
    sched = AwsLambdaDeferredTaskScheduler(function_name="fn", lambda_client=client)
    with pytest.raises(TaskDispatchError):
        sched.schedule("t.task", {"k": "v"}, strict=True)


@pytest.mark.parametrize("response", [{"StatusCode": 200}, {"StatusCode": 202}])
def test_accepted_invoke_response_is_not_a_failure(response):
    client = MagicMock()
    client.invoke.return_value = response
    sched = AwsLambdaDeferredTaskScheduler(function_name="fn", lambda_client=client)
    assert sched.schedule("t.task", {"k": "v"}, strict=True).startswith("aws-lambda-")


def test_non_strict_ignores_rejected_invoke_response():
    client = MagicMock()
    client.invoke.return_value = {"StatusCode": 500}
    sched = AwsLambdaDeferredTaskScheduler(function_name="fn", lambda_client=client)
    assert sched.schedule("t.task", {"k": "v"}).startswith("aws-lambda-")


# ── EventBridge failure must not silently become a doomed immediate invoke ───


def test_strict_raises_when_eventbridge_fails_beyond_lambda_timeout():
    """A far-future task cannot be honored by invoking now and waiting."""
    client = MagicMock()
    client.invoke.return_value = {"StatusCode": 202}
    sched = AwsLambdaDeferredTaskScheduler(function_name="fn", lambda_client=client)
    with patch(
        "jvspatial.serverless.tasks.aws_lambda._create_eventbridge_schedule",
        return_value=False,
    ):
        with pytest.raises(TaskDispatchError, match="EventBridge"):
            sched.schedule("t.task", {"k": "v"}, delay_seconds=3600, strict=True)
    client.invoke.assert_not_called()


def test_strict_allows_short_delay_fallback_to_immediate_invoke():
    """Inside the Lambda timeout the handler can honor process_at itself."""
    client = MagicMock()
    client.invoke.return_value = {"StatusCode": 202}
    sched = AwsLambdaDeferredTaskScheduler(function_name="fn", lambda_client=client)
    with patch(
        "jvspatial.serverless.tasks.aws_lambda._create_eventbridge_schedule",
        return_value=False,
    ):
        ref = sched.schedule("t.task", {"k": "v"}, delay_seconds=30, strict=True)
    assert ref.startswith("aws-lambda-")
    client.invoke.assert_called_once()


def test_non_strict_still_falls_back_for_a_far_future_task():
    client = MagicMock()
    client.invoke.return_value = {"StatusCode": 202}
    sched = AwsLambdaDeferredTaskScheduler(function_name="fn", lambda_client=client)
    with patch(
        "jvspatial.serverless.tasks.aws_lambda._create_eventbridge_schedule",
        return_value=False,
    ):
        ref = sched.schedule("t.task", {"k": "v"}, delay_seconds=3600)
    assert ref.startswith("aws-lambda-")
    client.invoke.assert_called_once()
