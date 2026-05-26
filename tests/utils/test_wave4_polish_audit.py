"""Wave 4 polish (audit §3.11, §7.7, §5.14)."""

import warnings

import pytest

from jvspatial.utils.stability import (
    ExperimentalWarning,
    emit_experimental_once,
    reset_experimental_warnings,
)


def test_emit_experimental_once_is_public():
    """Public hook so callers can flag opt-in surface without reaching
    into ``_emit_once`` (audit §7.7)."""
    reset_experimental_warnings()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ExperimentalWarning)
        emit_experimental_once("test.api.public_hook", "note")
        emit_experimental_once("test.api.public_hook", "note")
    # Single emission per (name) regardless of repeated calls.
    assert sum(1 for w in caught if issubclass(w.category, ExperimentalWarning)) == 1


@pytest.mark.asyncio
async def test_generate_id_async_emits_deprecation():
    """``generate_id_async`` is a deprecated alias for ``generate_id``
    (audit §3.11). It must still work — the call site only sees a
    warning."""
    from jvspatial.core.utils import generate_id_async

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        result = await generate_id_async("n", "Demo")
    assert result.startswith("n.Demo.")
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_jsontransaction_dead_class_removed():
    """``JSONTransaction`` was unused dead code (audit §5.14). Must no
    longer be exported from ``jvspatial.db.transaction``."""
    import jvspatial.db.transaction as txn_mod

    assert "JSONTransaction" not in txn_mod.__all__
    assert not hasattr(txn_mod, "JSONTransaction")
