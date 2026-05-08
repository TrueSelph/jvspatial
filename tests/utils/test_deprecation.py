"""Tests for jvspatial.utils.deprecation.deprecated decorator."""

import warnings
from unittest.mock import patch

import pytest

from jvspatial.utils.deprecation import (
    deprecated,
    reset_deprecation_warnings,
)


@pytest.fixture(autouse=True)
def reset_state():
    reset_deprecation_warnings()
    yield
    reset_deprecation_warnings()


class TestSyncFunction:
    def test_first_call_emits_deprecation_warning(self):
        @deprecated(
            replacement="new_thing()",
            remove_in="0.99.0",
            name="test.api.dep_first",
        )
        def f():
            return 1

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            assert f() == 1
        assert len(caught) == 1
        msg = str(caught[0].message)
        assert "test.api.dep_first" in msg
        assert "new_thing()" in msg
        assert "0.99.0" in msg

    def test_second_call_silent(self):
        @deprecated(name="test.api.dep_silent")
        def f():
            return 1

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            f()
            f()
            f()
        assert len(caught) == 1

    def test_message_with_no_metadata_still_renders(self):
        @deprecated(name="test.api.dep_bare")
        def f():
            return 1

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            f()
        assert "Will be removed" in str(caught[0].message)


class TestAsyncFunction:
    @pytest.mark.asyncio
    async def test_async_first_call_emits(self):
        @deprecated(
            replacement="new_async()",
            name="test.api.dep_async",
        )
        async def f():
            return "ok"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            assert await f() == "ok"
        assert len(caught) == 1


class TestServerlessSuppression:
    def test_suppressed_in_serverless_mode(self):
        @deprecated(name="test.api.dep_serverless")
        def f():
            return 1

        with patch(
            "jvspatial.utils.deprecation.is_serverless_mode",
            return_value=True,
        ):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", DeprecationWarning)
                f()
                f()
        assert caught == []
