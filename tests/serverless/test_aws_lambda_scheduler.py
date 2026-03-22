"""Tests for AwsLambdaDeferredTaskScheduler."""

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from jvspatial.env import clear_load_env_cache
from jvspatial.runtime.serverless import reset_serverless_mode_cache
from jvspatial.serverless.tasks.aws_lambda import AwsLambdaDeferredTaskScheduler


@pytest.fixture(autouse=True)
def _clear_serverless_caches():
    reset_serverless_mode_cache()
    clear_load_env_cache()
    yield
    reset_serverless_mode_cache()
    clear_load_env_cache()


def test_schedule_invoke_without_function_name_logs():
    sched = AwsLambdaDeferredTaskScheduler(function_name="")
    ref = sched.schedule("t.example", {"a": 1})
    assert ref.startswith("aws-lambda-")


def test_schedule_lambda_invoke_payload_merges_dict():
    mock_client = MagicMock()
    sched = AwsLambdaDeferredTaskScheduler(
        function_name="fn",
        lambda_client=mock_client,
    )
    sched.schedule(
        "jvagent.whatsapp.media_batch",
        {"sender": "u1", "media_batch_window": 1.5},
        run_at=12345.0,
    )
    mock_client.invoke.assert_called_once()
    call_kw = mock_client.invoke.call_args.kwargs
    assert call_kw["FunctionName"] == "fn"
    assert call_kw["InvocationType"] == "Event"
    body = json.loads(call_kw["Payload"])
    assert body["task_type"] == "jvagent.whatsapp.media_batch"
    assert body["sender"] == "u1"
    assert body["media_batch_window"] == 1.5
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
        clear_load_env_cache()
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
