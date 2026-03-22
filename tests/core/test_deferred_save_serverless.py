"""DeferredSaveMixin behavior under serverless vs non-serverless mode."""

import os
from unittest.mock import patch

import pytest

from jvspatial.core.mixins.deferred_save import (
    DeferredSaveMixin,
    deferred_saves_globally_allowed,
    flush_deferred_entities,
)
from jvspatial.env import clear_load_env_cache
from jvspatial.runtime.serverless import reset_serverless_mode_cache


class _SaveCounterBase:
    """Minimal base with async save for MRO below DeferredSaveMixin."""

    def __init__(self) -> None:
        self.save_calls = 0

    async def save(self, *args, **kwargs):
        self.save_calls += 1
        return "ok"


class _DeferredEntity(DeferredSaveMixin, _SaveCounterBase):
    """Concrete entity using deferred save mixin."""


class _DeferredNoAutoInit(DeferredSaveMixin, _SaveCounterBase):
    """Deferred mixin with auto-init disabled (opt-out)."""

    deferred_saves_auto_on_init = False


@pytest.fixture(autouse=True)
def _reset_serverless_cache():
    reset_serverless_mode_cache()
    clear_load_env_cache()
    yield
    reset_serverless_mode_cache()
    clear_load_env_cache()


def test_deferred_saves_globally_allowed_false_in_serverless():
    with patch.dict(os.environ, {"SERVERLESS_MODE": "true"}, clear=False):
        reset_serverless_mode_cache()
        clear_load_env_cache()
        assert deferred_saves_globally_allowed() is False


def test_deferred_saves_globally_allowed_respects_env_off():
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "false"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        clear_load_env_cache()
        assert deferred_saves_globally_allowed() is False


def test_deferred_saves_globally_allowed_true_when_env_on_and_not_serverless():
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        clear_load_env_cache()
        assert deferred_saves_globally_allowed() is True


def test_deferred_mode_on_at_construct_when_globally_allowed():
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        clear_load_env_cache()
        entity = _DeferredEntity()
        assert entity.deferred_saves_enabled is True


def test_deferred_auto_init_disabled_class_opt_out():
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        clear_load_env_cache()
        entity = _DeferredNoAutoInit()
        assert entity.deferred_saves_enabled is False


@pytest.mark.asyncio
async def test_save_immediate_in_serverless():
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "true", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true"},
        clear=False,
    ):
        reset_serverless_mode_cache()
        clear_load_env_cache()
        entity = _DeferredEntity()
        entity.enable_deferred_saves()
        assert entity.deferred_saves_enabled is False
        await entity.save()
        assert entity.save_calls == 1
        assert entity.is_dirty is False


@pytest.mark.asyncio
async def test_save_deferred_when_allowed_and_enabled():
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        clear_load_env_cache()
        entity = _DeferredEntity()
        assert entity.deferred_saves_enabled is True
        await entity.save()
        assert entity.save_calls == 0
        assert entity.is_dirty is True
        await entity.flush()
        assert entity.save_calls == 1
        assert entity.is_dirty is False


@pytest.mark.asyncio
async def test_enable_deferred_saves_after_flush_restores_batching():
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        clear_load_env_cache()
        entity = _DeferredEntity()
        assert entity.deferred_saves_enabled is True
        await entity.flush()
        assert entity.deferred_saves_enabled is False
        entity.enable_deferred_saves()
        assert entity.deferred_saves_enabled is True
        await entity.save()
        assert entity.save_calls == 0


@pytest.mark.asyncio
async def test_flush_clears_deferred_mode_when_not_dirty():
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        clear_load_env_cache()
        entity = _DeferredEntity()
        assert entity.deferred_saves_enabled is True
        await entity.flush()
        assert entity.deferred_saves_enabled is False
        assert entity.is_dirty is False
        assert entity.save_calls == 0
        await entity.save()
        assert entity.save_calls == 1


@pytest.mark.asyncio
async def test_flush_deferred_entities_non_strict_continues_after_failure():
    class _Flaky(_DeferredEntity):
        async def flush(self) -> None:
            raise RuntimeError("flush fail")

    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        clear_load_env_cache()
        bad = _Flaky()
        good = _DeferredEntity()
        ok = await flush_deferred_entities(bad, good, strict=False)
        assert ok is False
        assert good.save_calls == 0


@pytest.mark.asyncio
async def test_flush_deferred_entities_strict_raises():
    class _Flaky(_DeferredEntity):
        async def flush(self) -> None:
            raise RuntimeError("flush fail")

    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        clear_load_env_cache()
        bad = _Flaky()
        good = _DeferredEntity()
        with pytest.raises(RuntimeError, match="flush fail"):
            await flush_deferred_entities(bad, good, strict=True)
