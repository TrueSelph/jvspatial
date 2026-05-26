"""Walker polish (audit §2.9, §2.10)."""

import pytest

from jvspatial.core.entities import TraversalSkipped, Walker


class _DemoWalker(Walker):
    pass


@pytest.mark.asyncio
async def test_walker_skip_raises_traversal_skipped():
    w = _DemoWalker()
    with pytest.raises(TraversalSkipped):
        await w.skip()


def test_walker_type_code_locked_to_w():
    w = _DemoWalker()
    assert w.type_code == "w"
    assert w.id.startswith("w.")


def test_walker_rejects_alternate_type_code():
    """Caller cannot smuggle a different ``type_code`` past the SPEC
    §1.1 invariant (audit §2.10)."""
    with pytest.raises(ValueError, match="type_code must be 'w'"):
        _DemoWalker(type_code="n")
