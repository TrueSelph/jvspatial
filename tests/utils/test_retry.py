"""Tests for the shared retry helper."""

import asyncio
from unittest.mock import patch

import pytest

from jvspatial.utils.retry import retry, retry_async


class _Transient(Exception):
    pass


class _Permanent(Exception):
    pass


class TestSuccessFastPath:
    async def test_no_retry_when_first_call_succeeds(self):
        calls = {"n": 0}

        async def f():
            calls["n"] += 1
            return "ok"

        result = await retry_async(f, retry_on=_Transient, max_attempts=5)
        assert result == "ok"
        assert calls["n"] == 1


class TestRetriesOnRetryable:
    async def test_retries_then_succeeds(self):
        calls = {"n": 0}

        async def f():
            calls["n"] += 1
            if calls["n"] < 3:
                raise _Transient("flap")
            return "ok"

        # Patch sleep so the test doesn't actually wait.
        with patch("jvspatial.utils.retry.asyncio.sleep", new=_no_sleep):
            result = await retry_async(
                f, retry_on=_Transient, max_attempts=5, base_delay=0.001
            )
        assert result == "ok"
        assert calls["n"] == 3

    async def test_gives_up_after_max_attempts(self):
        calls = {"n": 0}

        async def f():
            calls["n"] += 1
            raise _Transient("forever")

        with patch("jvspatial.utils.retry.asyncio.sleep", new=_no_sleep):
            with pytest.raises(_Transient):
                await retry_async(
                    f, retry_on=_Transient, max_attempts=4, base_delay=0.001
                )
        assert calls["n"] == 4


class TestNonRetryable:
    async def test_non_retryable_propagates_immediately(self):
        calls = {"n": 0}

        async def f():
            calls["n"] += 1
            raise _Permanent("broken")

        with pytest.raises(_Permanent):
            await retry_async(f, retry_on=_Transient, max_attempts=5)
        assert calls["n"] == 1


class TestPredicateRetryOn:
    async def test_callable_predicate(self):
        calls = {"n": 0}

        async def f():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("retry-please-error-123")
            return "ok"

        def is_retryable(exc):
            return "retry-please" in str(exc)

        with patch("jvspatial.utils.retry.asyncio.sleep", new=_no_sleep):
            result = await retry_async(
                f, retry_on=is_retryable, max_attempts=5, base_delay=0.001
            )
        assert result == "ok"
        assert calls["n"] == 3

    async def test_callable_predicate_rejects(self):
        async def f():
            raise ValueError("nope")

        def never(exc):
            return False

        with pytest.raises(ValueError):
            await retry_async(f, retry_on=never, max_attempts=5)


class TestBackoffSchedule:
    async def test_exponential_backoff_observable(self):
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        async def f():
            raise _Transient("flap")

        with patch("jvspatial.utils.retry.asyncio.sleep", new=fake_sleep):
            with pytest.raises(_Transient):
                await retry_async(
                    f,
                    retry_on=_Transient,
                    max_attempts=4,
                    base_delay=1.0,
                    max_delay=100.0,
                    jitter=False,
                )
        # No-jitter schedule for max_attempts=4: sleeps after attempts 1,2,3
        # i.e. base*2^0, base*2^1, base*2^2.
        assert sleeps == [1.0, 2.0, 4.0]

    async def test_max_delay_caps_backoff(self):
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        async def f():
            raise _Transient("flap")

        with patch("jvspatial.utils.retry.asyncio.sleep", new=fake_sleep):
            with pytest.raises(_Transient):
                await retry_async(
                    f,
                    retry_on=_Transient,
                    max_attempts=6,
                    base_delay=1.0,
                    max_delay=3.0,
                    jitter=False,
                )
        # All sleeps are capped at 3.0
        assert all(s <= 3.0 for s in sleeps)
        assert sleeps[-1] == 3.0


class TestDecoratorForm:
    async def test_decorator_retries(self):
        calls = {"n": 0}

        @retry(retry_on=_Transient, max_attempts=4, base_delay=0.001)
        async def f():
            calls["n"] += 1
            if calls["n"] < 3:
                raise _Transient("flap")
            return "ok"

        with patch("jvspatial.utils.retry.asyncio.sleep", new=_no_sleep):
            result = await f()
        assert result == "ok"
        assert calls["n"] == 3


class TestOnRetryHook:
    async def test_hook_called_with_attempt_and_sleep(self):
        recorded = []

        async def f():
            raise _Transient("flap")

        def hook(exc, attempt, sleep_for):
            recorded.append((type(exc).__name__, attempt, sleep_for))

        with patch("jvspatial.utils.retry.asyncio.sleep", new=_no_sleep):
            with pytest.raises(_Transient):
                await retry_async(
                    f,
                    retry_on=_Transient,
                    max_attempts=3,
                    base_delay=0.001,
                    on_retry=hook,
                )
        # Hook fires before each retry sleep -> max_attempts - 1 times.
        assert len(recorded) == 2
        assert all(r[0] == "_Transient" for r in recorded)
        assert recorded[0][1] == 1  # attempt that just failed
        assert recorded[1][1] == 2


class TestArgValidation:
    async def test_bad_max_attempts(self):
        async def f():
            return 1

        with pytest.raises(ValueError):
            await retry_async(f, retry_on=_Transient, max_attempts=0)

    async def test_bad_retry_on(self):
        async def f():
            return 1

        with pytest.raises(TypeError):
            await retry_async(f, retry_on="not-an-exception", max_attempts=3)


# ----- helpers --------------------------------------------------------


async def _no_sleep(seconds):
    """Drop-in replacement for asyncio.sleep that returns immediately."""
    return None
