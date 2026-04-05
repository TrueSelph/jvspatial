"""Tests for deferred task scheduler factory and provider detection."""

import os
from unittest.mock import MagicMock, patch

import pytest

from jvspatial.runtime.serverless import (
    detect_serverless_provider,
    reset_serverless_mode_cache,
)
from jvspatial.serverless.factory import dispatch_deferred_task, get_task_scheduler
from jvspatial.serverless.tasks.aws_lambda import AwsLambdaDeferredTaskScheduler
from jvspatial.serverless.tasks.aws_sqs import AwsSqsTaskScheduler
from jvspatial.serverless.tasks.stub import LoggingNoopTaskScheduler
from jvspatial.serverless.tasks.sync import NoopOrSyncScheduler


@pytest.fixture(autouse=True)
def _clear_serverless_caches():
    reset_serverless_mode_cache()
    yield
    reset_serverless_mode_cache()


def test_detect_serverless_provider_aws_lambda():
    with patch.dict(
        os.environ,
        {"AWS_LAMBDA_FUNCTION_NAME": "x"},
        clear=False,
    ):
        reset_serverless_mode_cache()
        assert detect_serverless_provider() == "aws"


def test_detect_serverless_provider_azure():
    with patch.dict(
        os.environ,
        {"FUNCTIONS_WORKER_RUNTIME": "python"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        assert detect_serverless_provider() == "azure"


def test_get_task_scheduler_override():
    mock_sched = MagicMock()
    assert get_task_scheduler(override=mock_sched) is mock_sched


def test_get_task_scheduler_injected_on_config():
    mock_sched = MagicMock()
    cfg = MagicMock()
    cfg.task_scheduler = mock_sched
    assert get_task_scheduler(cfg) is mock_sched


def test_get_task_scheduler_non_serverless_is_noop():
    with patch.dict(os.environ, {"SERVERLESS_MODE": "false"}, clear=False):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        s = get_task_scheduler()
        assert isinstance(s, NoopOrSyncScheduler)


def test_get_task_scheduler_serverless_aws_lambda():
    with patch.dict(
        os.environ,
        {
            "SERVERLESS_MODE": "true",
            "AWS_LAMBDA_FUNCTION_NAME": "my-fn",
            "JVSPATIAL_AWS_DEFERRED_TRANSPORT": "lambda_invoke",
        },
        clear=False,
    ):
        reset_serverless_mode_cache()
        s = get_task_scheduler()
        assert isinstance(s, AwsLambdaDeferredTaskScheduler)


def test_get_task_scheduler_serverless_aws_sqs_transport():
    with patch.dict(
        os.environ,
        {
            "SERVERLESS_MODE": "true",
            "JVSPATIAL_DEFERRED_TASK_PROVIDER": "aws",
            "JVSPATIAL_AWS_DEFERRED_TRANSPORT": "sqs",
            "JVSPATIAL_AWS_SQS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123/q",
        },
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        with patch(
            "jvspatial.serverless.factory._make_sqs_scheduler",
            side_effect=lambda url: AwsSqsTaskScheduler(MagicMock(), url),
        ):
            s = get_task_scheduler()
            assert isinstance(s, AwsSqsTaskScheduler)


def test_get_task_scheduler_provider_override_azure():
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "true", "JVSPATIAL_DEFERRED_TASK_PROVIDER": "azure"},
        clear=False,
    ):
        reset_serverless_mode_cache()
        s = get_task_scheduler()
        assert isinstance(s, LoggingNoopTaskScheduler)


def test_config_deferred_task_provider_field():
    from jvspatial.api.config import ServerConfig

    cfg = ServerConfig(deferred_task_provider="azure")
    with patch.dict(os.environ, {"SERVERLESS_MODE": "true"}, clear=False):
        os.environ.pop("JVSPATIAL_DEFERRED_TASK_PROVIDER", None)
        reset_serverless_mode_cache()
        s = get_task_scheduler(cfg)
        assert isinstance(s, LoggingNoopTaskScheduler)


def test_dispatch_deferred_task_strict_raises_on_noop_scheduler():
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "true", "JVSPATIAL_DEFERRED_TASK_PROVIDER": "azure"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        with pytest.raises(RuntimeError, match="no-op"):
            dispatch_deferred_task("task.x", {}, strict=True)
