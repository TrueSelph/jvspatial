"""Regression coverage for Wave 1 walker-protection fixes (audit §2).

The earlier implementation:

* Swallowed every ``ProtectionViolation`` into ``walker.report``, so callers
  never saw ``InfiniteLoopError`` / ``WalkerTimeoutError`` / ``WalkerExecutionError``
  even though SPEC §6.3 promised them.
* Called ``self._protection.reset()`` at the top of ``Walker.run()``. ``resume()``
  re-enters ``run()`` → resetting step / visit counters and the wall-clock timer.
  Repeated pause/resume cycles cleared protection state, trivially defeating the
  cap.
* Ignored ``max_trail_length`` — the docstring promised it, no code wired it.
* Allowed ``WalkerQueue.prepend`` / ``add_next`` / ``insert_after`` / ``insert_before``
  to grow past ``max_size``, providing a silent protection bypass.

These tests pin the corrected behavior so future regressions are loud.
"""

import asyncio

import pytest

from jvspatial.core.entities import Node, Walker
from jvspatial.core.entities.walker_components.protection import (
    ProtectionViolation,
    TraversalProtection,
)
from jvspatial.core.entities.walker_components.walker_queue import WalkerQueue
from jvspatial.core.entities.walker_components.walker_trail import WalkerTrail
from jvspatial.exceptions import (
    InfiniteLoopError,
    WalkerExecutionError,
    WalkerTimeoutError,
)

# ---------- TraversalProtection ----------


@pytest.mark.asyncio
async def test_start_if_needed_is_idempotent():
    prot = TraversalProtection(max_steps=10)
    await prot.start_if_needed()
    first_start = prot._start_time
    await prot.increment_step()
    await prot.increment_step()
    assert prot.step_count == 2

    # Calling start_if_needed again must NOT reset counters or restart the
    # wall-clock timer. Previously ``run()`` called ``reset()`` which did.
    await prot.start_if_needed()
    assert prot.step_count == 2
    assert prot._start_time == first_start


@pytest.mark.asyncio
async def test_reset_is_still_available_for_explicit_restart():
    prot = TraversalProtection(max_steps=10)
    await prot.start_if_needed()
    await prot.increment_step()
    await prot.reset()
    # Explicit reset starts a fresh session — start_if_needed becomes a no-op
    # after reset because reset sets _started = True.
    assert prot.step_count == 0


# ---------- Walker.run() raises documented exceptions ----------


class AlwaysReenqueueNode(Node):
    name: str = ""


class TightLoopWalker(Walker):
    """Visits the same node repeatedly so max_visits_per_node fires."""

    async def visit(self, target):
        await self.queue.append([target])


@pytest.mark.asyncio
async def test_walker_run_raises_infinite_loop_error_on_visit_cap():
    node = AlwaysReenqueueNode(name="cycle")
    walker = TightLoopWalker(max_visits_per_node=3)
    # Seed the queue with the same node many times so record_visit hits the cap.
    await walker.queue.append([node] * 20)

    with pytest.raises(InfiniteLoopError) as exc_info:
        await walker.run()
    err = exc_info.value
    assert err.node_id == node.id
    assert err.walker_class == "TightLoopWalker"


@pytest.mark.asyncio
async def test_walker_run_raises_walker_execution_error_on_step_cap():
    walker = TightLoopWalker(max_steps=3, max_visits_per_node=10_000)
    # Distinct nodes so visit-cap does not fire first.
    nodes = [AlwaysReenqueueNode(name=f"n{i}") for i in range(20)]
    await walker.queue.append(nodes)

    with pytest.raises(WalkerExecutionError) as exc_info:
        await walker.run()
    assert "max_steps" in exc_info.value.reason


# ---------- max_trail_length wired ----------


def test_walker_trail_unbounded_by_default():
    trail = WalkerTrail()
    for i in range(50):
        trail.record_step(f"n.X.{i}")
    assert trail.get_length() == 50


def test_walker_trail_respects_max_length():
    trail = WalkerTrail(max_length=10)
    for i in range(50):
        trail.record_step(f"n.X.{i}")
    # Only the most recent 10 retained.
    assert trail.get_length() == 10
    most_recent_ids = [step["node"] for step in trail.get_trail()]
    assert most_recent_ids[0] == "n.X.40"
    assert most_recent_ids[-1] == "n.X.49"


def test_walker_propagates_max_trail_length():
    """Walker.__init__ pops ``max_trail_length`` and rebuilds the trail tracker."""
    walker = TightLoopWalker(max_trail_length=3)
    for i in range(10):
        walker._trail_tracker.record_step(f"n.X.{i}")
    assert walker._trail_tracker.get_length() == 3


# ---------- WalkerQueue inserts respect max_size ----------


@pytest.mark.asyncio
async def test_prepend_respects_max_size():
    q = WalkerQueue(max_size=3)
    await q.visit(["a", "b", "c"])
    # Past cap — prepend must drop, not silently grow.
    await q.prepend(["x", "y"])
    assert len(q) == 3
    # Existing items preserved at the head's downstream side.
    assert list(q.to_list()) == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_add_next_respects_max_size():
    q = WalkerQueue(max_size=2)
    await q.visit(["a", "b"])
    await q.add_next(["x"])
    assert len(q) == 2


@pytest.mark.asyncio
async def test_insert_after_respects_max_size_and_returns_inserted():
    q = WalkerQueue(max_size=3)
    await q.visit(["a", "b", "c"])
    inserted = await q.insert_after("a", ["x", "y"])
    assert inserted == []  # No room.
    assert len(q) == 3


@pytest.mark.asyncio
async def test_insert_before_respects_max_size_and_returns_inserted():
    q = WalkerQueue(max_size=4)
    await q.visit(["a", "b"])
    inserted = await q.insert_before("b", ["x", "y", "z"])
    # First two fit (filling the 4-slot cap), third is dropped.
    assert inserted == ["x", "y"]
    assert len(q) == 4
