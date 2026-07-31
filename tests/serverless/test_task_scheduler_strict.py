"""Strict dispatch semantics across every scheduler and through the factory.

``strict=True`` is the caller stating it has its own failure handling and that
a silently-dropped task is data loss. That guarantee is only worth anything if
it holds on *every* transport and survives the factory, so these cases cover
the adapters the Lambda-specific suite does not, plus the
``dispatch_deferred_task`` plumbing itself.
"""

from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from jvspatial.exceptions import (
    DeferredTaskError,
    TaskDispatchError,
    TaskSchedulerNotConfiguredError,
)
from jvspatial.runtime.serverless import reset_serverless_mode_cache
from jvspatial.serverless.factory import dispatch_deferred_task
from jvspatial.serverless.tasks.aws_sqs import AwsSqsTaskScheduler
from jvspatial.serverless.tasks.base import RetryConfig, TaskScheduler
from jvspatial.serverless.tasks.stub import LoggingNoopTaskScheduler
from jvspatial.serverless.tasks.sync import NoopOrSyncScheduler


@pytest.fixture(autouse=True)
def _clear_serverless_caches():
    reset_serverless_mode_cache()
    yield
    reset_serverless_mode_cache()


# ── SQS ─────────────────────────────────────────────────────────────────────


def test_sqs_strict_raises_when_client_unconfigured():
    sched = AwsSqsTaskScheduler(sqs_client=None, queue_url=None)
    with pytest.raises(TaskSchedulerNotConfiguredError, match="SQS"):
        sched.schedule("t.task", {"k": "v"}, strict=True)


def test_sqs_non_strict_returns_reference_when_unconfigured():
    sched = AwsSqsTaskScheduler(sqs_client=None, queue_url=None)
    assert sched.schedule("t.task", {"k": "v"}).startswith("aws-sqs-")


def test_sqs_strict_raises_on_send_message_failure():
    client = MagicMock()
    client.send_message.side_effect = RuntimeError("throttled")
    sched = AwsSqsTaskScheduler(sqs_client=client, queue_url="https://q")
    with pytest.raises(TaskDispatchError, match="send_message"):
        sched.schedule("t.task", {"k": "v"}, strict=True)


def test_sqs_non_strict_swallows_send_message_failure():
    """Fire-and-forget is now the non-strict contract on every transport.

    Previously SQS propagated while the Lambda transport swallowed, so the
    same application code had opposite semantics depending on
    ``JVSPATIAL_AWS_DEFERRED_TRANSPORT``.
    """
    client = MagicMock()
    client.send_message.side_effect = RuntimeError("throttled")
    sched = AwsSqsTaskScheduler(sqs_client=client, queue_url="https://q")
    assert sched.schedule("t.task", {"k": "v"}).startswith("aws-sqs-")


def test_sqs_success_sends_and_returns_reference():
    client = MagicMock()
    sched = AwsSqsTaskScheduler(sqs_client=client, queue_url="https://q")
    ref = sched.schedule("t.task", {"k": "v"}, strict=True)
    assert ref.startswith("aws-sqs-")
    client.send_message.assert_called_once()


# ── logging no-op ───────────────────────────────────────────────────────────


def test_stub_strict_raises():
    sched = LoggingNoopTaskScheduler("no transport configured")
    with pytest.raises(TaskSchedulerNotConfiguredError, match="no transport"):
        sched.schedule("t.task", {"k": "v"}, strict=True)


def test_stub_non_strict_returns_reference():
    sched = LoggingNoopTaskScheduler()
    assert sched.schedule("t.task", {"k": "v"}).startswith("noop-")


# ── sync / no-op fallback ───────────────────────────────────────────────────


def test_sync_without_executor_raises_under_strict():
    """The shape every non-serverless caller gets: nothing would run."""
    sched = NoopOrSyncScheduler(None)
    with pytest.raises(TaskSchedulerNotConfiguredError, match="no executor"):
        sched.schedule("t.task", {"k": "v"}, strict=True)


def test_sync_without_executor_is_still_fire_and_forget_by_default():
    sched = NoopOrSyncScheduler(None)
    assert sched.schedule("t.task", {"k": "v"}).startswith("sync-")


def test_sync_with_executor_satisfies_strict():
    """The work happened in-process before schedule() returned."""
    seen = []
    sched = NoopOrSyncScheduler(lambda t, p: seen.append((t, p)))
    ref = sched.schedule("t.task", {"k": "v"}, strict=True)
    assert ref.startswith("sync-")
    assert seen == [("t.task", {"k": "v"})]


# ── factory plumbing ────────────────────────────────────────────────────────


class _RecordingScheduler(TaskScheduler):
    """Current-signature scheduler that records what it was handed."""

    def __init__(self) -> None:
        self.calls: list = []

    def schedule(
        self,
        task_type: str,
        payload: Any,
        delay_seconds: int = 0,
        retry_config: Optional[RetryConfig] = None,
        run_at: Optional[float] = None,
        strict: bool = False,
    ) -> str:
        self.calls.append({"task_type": task_type, "strict": strict})
        return "recorded"


class _LegacyScheduler:
    """Third-party scheduler written against the pre-``strict`` signature."""

    def __init__(self) -> None:
        self.calls: list = []

    def schedule(
        self,
        task_type: str,
        payload: Any,
        delay_seconds: int = 0,
        retry_config: Optional[RetryConfig] = None,
        run_at: Optional[float] = None,
    ) -> str:
        self.calls.append(task_type)
        return "legacy"


class _KwargsScheduler:
    """Scheduler that absorbs unknown keywords."""

    def __init__(self) -> None:
        self.calls: list = []

    def schedule(self, task_type: str, payload: Any, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return "kwargs"


@pytest.mark.parametrize("strict", [False, True])
def test_dispatch_forwards_strict_to_a_modern_scheduler(strict):
    sched = _RecordingScheduler()
    assert (
        dispatch_deferred_task("t.task", {"k": "v"}, override=sched, strict=strict)
        == "recorded"
    )
    assert sched.calls == [{"task_type": "t.task", "strict": strict}]


def test_dispatch_omits_strict_for_a_legacy_scheduler():
    """A pre-``strict`` third-party scheduler must keep working.

    ``TaskScheduler`` is public/stable and ``config.task_scheduler`` is
    duck-typed, so forwarding ``strict=`` unconditionally would raise
    ``TypeError`` on every dispatch — including non-strict ones.
    """
    sched = _LegacyScheduler()
    assert dispatch_deferred_task("t.task", {"k": "v"}, override=sched) == "legacy"
    assert sched.calls == ["t.task"]


def test_dispatch_refuses_strict_on_a_legacy_scheduler():
    """It cannot honor the guarantee, so say so instead of pretending."""
    sched = _LegacyScheduler()
    with pytest.raises(TaskSchedulerNotConfiguredError, match="does not accept"):
        dispatch_deferred_task("t.task", {"k": "v"}, override=sched, strict=True)
    assert sched.calls == []


def test_dispatch_forwards_strict_to_a_kwargs_scheduler():
    sched = _KwargsScheduler()
    assert (
        dispatch_deferred_task("t.task", {"k": "v"}, override=sched, strict=True)
        == "kwargs"
    )
    assert sched.calls[0]["strict"] is True


def test_deferred_task_errors_are_runtime_errors():
    """Handlers written against the previous bare-RuntimeError raise still work."""
    assert issubclass(DeferredTaskError, RuntimeError)
    assert issubclass(TaskDispatchError, DeferredTaskError)
    assert issubclass(TaskSchedulerNotConfiguredError, TaskDispatchError)
