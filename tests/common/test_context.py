"""Test suite for common context utilities."""

import pytest

from jvspatial.common.context import GlobalContext


class TestGlobalContext:
    """Test GlobalContext functionality."""

    def test_global_context_initialization(self):
        """Test global context initialization."""

        def factory():
            return "test_value"

        context = GlobalContext(factory, "test")
        assert context is not None
        assert context._name == "test"

    def test_global_context_get(self):
        """Test getting context value."""

        def factory():
            return "test_value"

        context = GlobalContext(factory, "test")
        value = context.get()
        assert value == "test_value"

    def test_global_context_set(self):
        """Test setting context value."""

        def factory():
            return "default_value"

        context = GlobalContext(factory, "test")
        context.set("custom_value")

        value = context.get()
        assert value == "custom_value"

    def test_global_context_clear(self):
        """Test clearing context value."""

        def factory():
            return "test_value"

        context = GlobalContext(factory, "test")
        context.set("custom_value")
        context.clear()

        value = context.get()
        assert value == "test_value"

    def test_global_context_override(self):
        """Test context override."""

        def factory():
            return "default_value"

        context = GlobalContext(factory, "test")

        with context.override("override_value"):
            value = context.get()
            assert value == "override_value"

        # Should return to default after override
        value = context.get()
        assert value == "default_value"
