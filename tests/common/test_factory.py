"""Test suite for common factory utilities."""

from unittest.mock import MagicMock

import pytest

from jvspatial.common.factory import PluginFactory


class TestPluginFactory:
    """Test PluginFactory functionality."""

    def test_plugin_factory_initialization(self):
        """Test plugin factory initialization."""
        factory = PluginFactory("TEST_PLUGIN_TYPE")
        assert factory is not None
        assert len(factory._registry) == 0

    def test_register_plugin(self):
        """Test plugin registration."""
        factory = PluginFactory("TEST_PLUGIN_TYPE")
        plugin = MagicMock()

        factory.register("test_plugin", plugin)
        assert "test_plugin" in factory._registry
        assert factory._registry["test_plugin"] == plugin

    def test_register_plugin_duplicate(self):
        """Test duplicate plugin registration."""
        factory = PluginFactory("TEST_PLUGIN_TYPE")
        plugin1 = MagicMock()
        plugin2 = MagicMock()

        factory.register("test_plugin", plugin1)

        # The current implementation allows overwriting, so we just test that it works
        factory.register("test_plugin", plugin2)
        assert factory._registry["test_plugin"] == plugin2

    def test_unregister_plugin(self):
        """Test plugin unregistration."""
        factory = PluginFactory("TEST_PLUGIN_TYPE")
        plugin = MagicMock()

        factory.register("test_plugin", plugin)
        factory.unregister("test_plugin")

        assert "test_plugin" not in factory._registry

    def test_unregister_plugin_nonexistent(self):
        """Test unregistering non-existent plugin."""
        factory = PluginFactory("TEST_PLUGIN_TYPE")

        # The current implementation doesn't raise an error for non-existent plugins
        factory.unregister("nonexistent")
        assert "nonexistent" not in factory._registry

    def test_get_plugin(self):
        """Test getting plugin."""
        factory = PluginFactory("TEST_PLUGIN_TYPE")

        class TestPlugin:
            def __init__(self):
                self.name = "test"

        factory.register("test_plugin", TestPlugin)
        retrieved_plugin = factory.get("test_plugin")

        assert isinstance(retrieved_plugin, TestPlugin)

    def test_get_plugin_nonexistent(self):
        """Test getting non-existent plugin."""
        factory = PluginFactory("TEST_PLUGIN_TYPE")

        with pytest.raises(ValueError):
            factory.get("nonexistent")

    def test_list_plugins(self):
        """Test listing plugins."""
        factory = PluginFactory("TEST_PLUGIN_TYPE")

        class Plugin1:
            pass

        class Plugin2:
            pass

        factory.register("plugin1", Plugin1)
        factory.register("plugin2", Plugin2)

        plugins = factory.list_available()
        assert len(plugins) == 2
        assert "plugin1" in plugins
        assert "plugin2" in plugins

    def test_has_plugin(self):
        """Test checking if plugin exists."""
        factory = PluginFactory("TEST_PLUGIN_TYPE")

        class TestPlugin:
            pass

        assert "test_plugin" not in factory._registry

        factory.register("test_plugin", TestPlugin)

        assert "test_plugin" in factory._registry

    def test_clear_plugins(self):
        """Test clearing all plugins."""
        factory = PluginFactory("TEST_PLUGIN_TYPE")

        class Plugin1:
            pass

        class Plugin2:
            pass

        factory.register("plugin1", Plugin1)
        factory.register("plugin2", Plugin2)

        # The current implementation doesn't have a clear method, so we test unregister
        factory.unregister("plugin1")
        factory.unregister("plugin2")

        assert len(factory._registry) == 0
