"""Tests for jvspatial.utils.stability.experimental decorator."""

import warnings
from unittest.mock import patch

import pytest

from jvspatial.utils.stability import (
    ExperimentalWarning,
    experimental,
    reset_experimental_warnings,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Each test starts with a clean once-per-process suppression set."""
    reset_experimental_warnings()
    yield
    reset_experimental_warnings()


class TestSyncFunction:
    def test_first_call_emits_warning(self):
        @experimental("test.api.first", "see issue #99")
        def f():
            return 42

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ExperimentalWarning)
            assert f() == 42

        assert len(caught) == 1
        assert issubclass(caught[0].category, ExperimentalWarning)
        assert "test.api.first" in str(caught[0].message)
        assert "see issue #99" in str(caught[0].message)

    def test_second_call_silent(self):
        @experimental("test.api.silent_after_first")
        def f():
            return 1

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ExperimentalWarning)
            f()
            f()
            f()
        assert len(caught) == 1

    def test_default_name_uses_qualname(self):
        @experimental()
        def f():
            return 1

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ExperimentalWarning)
            f()
        assert len(caught) == 1
        msg = str(caught[0].message)
        assert "f" in msg
        assert __name__ in msg

    def test_preserves_return_value_and_signature(self):
        @experimental("test.api.passthrough")
        def add(a, b, *, c=0):
            """Adds three numbers."""
            return a + b + c

        assert add(1, 2, c=3) == 6
        assert add.__doc__ == "Adds three numbers."
        assert add.__name__ == "add"


class TestAsyncFunction:
    @pytest.mark.asyncio
    async def test_async_first_call_emits(self):
        @experimental("test.api.async_first")
        async def f():
            return "async"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ExperimentalWarning)
            result = await f()
        assert result == "async"
        assert len(caught) == 1

    @pytest.mark.asyncio
    async def test_async_second_call_silent(self):
        @experimental("test.api.async_silent")
        async def f():
            return 1

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ExperimentalWarning)
            await f()
            await f()
        assert len(caught) == 1

    @pytest.mark.asyncio
    async def test_async_function_remains_coroutine_function(self):
        import asyncio

        @experimental("test.api.coro_check")
        async def f():
            return 1

        assert asyncio.iscoroutinefunction(f)


class TestServerlessSuppression:
    def test_no_warning_in_serverless_mode(self):
        @experimental("test.api.serverless_silent")
        def f():
            return 1

        with patch("jvspatial.utils.stability.is_serverless_mode", return_value=True):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ExperimentalWarning)
                f()
                f()
        assert caught == []


class TestUserSuppression:
    def test_user_can_silence_globally(self):
        @experimental("test.api.user_silenced")
        def f():
            return 1

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("ignore", ExperimentalWarning)
            f()
        assert caught == []
