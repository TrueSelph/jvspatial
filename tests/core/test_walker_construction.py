"""Walker construction must preserve isolation without evaluating descriptors."""

import inspect

from jvspatial.core import Walker, on_exit
from jvspatial.core.entities.walker import _class_functions
from jvspatial.core.events import on_emit


def test_class_function_discovery_preserves_inheritance_and_replacement():
    class Parent(Walker):
        @on_emit("example")
        def event(self, value):
            return value

        @on_exit
        def finished(self):
            pass

    class Child(Parent):
        def finished(self):
            pass

    expected = dict(inspect.getmembers(Child, inspect.isfunction))
    assert dict(_class_functions(Child)) == expected
    first, second = Child(), Child()
    assert first._event_handlers == second._event_handlers
    first._event_handlers.clear()
    first._report.append("one")
    assert second._event_handlers
    assert second._report == []
    assert first.queue is not second.queue
    assert first._trail_tracker is not second._trail_tracker

    @on_emit("new")
    def replacement(self, value):
        return value

    Child.event = replacement
    assert Child()._event_handlers == {"new": [replacement]}


def test_hook_discovery_does_not_evaluate_unrelated_descriptors():
    class Exploding:
        def __get__(self, instance, owner):
            raise RuntimeError("descriptor evaluated")

    # Attaching after model creation avoids changing Pydantic's field contract.
    class Example(Walker):
        pass

    Example.unrelated_descriptor = Exploding()
    assert list(_class_functions(Example))
    assert Example().get_trail() == []
