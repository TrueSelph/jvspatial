"""Tests for ``__entity_name__`` per-class override of the persisted entity discriminator.

Covers the case where two unrelated ``Node`` (or ``Object``) subclasses share a
Python class name and must remain distinguishable at the storage layer (e.g.
host-app ``App`` vs library ``App``). Setting ``__entity_name__`` on one of
them decouples ``cls.__name__`` from the ``entity`` field jvspatial uses to
discriminate rows.
"""

import tempfile
import uuid
from unittest.mock import patch

import pytest

from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Node
from jvspatial.core.utils import _class_entity_name, find_subclass_by_name
from jvspatial.db import create_database


# Two classes with the same Python ``__name__`` but distinct entity discriminators.
class App(Node):
    """Host-app App. Persists with the override entity name."""

    __entity_name__ = "HostApp"
    title: str = ""


# Define a second class also literally named ``App`` in this module's local scope
# by reusing the class statement. Pytest's collector preserves the binding so we
# rebind via type() to keep both alive.
_LibApp = type(
    "App",
    (Node,),
    {
        "__module__": __name__,
        "__doc__": "Library App. Persists with default entity name 'App'.",
        "__annotations__": {"label": str},
        "label": "",
    },
)


@pytest.fixture
def json_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        unique_path = f"{tmpdir}/test_{uuid.uuid4().hex}"
        database = create_database("json", base_path=unique_path)
        yield GraphContext(database=database)


def test_entity_name_helper_honors_override():
    assert _class_entity_name(App) == "HostApp"
    assert _class_entity_name(_LibApp) == "App"

    # Subclasses without their own override inherit ``__name__`` semantics,
    # NOT the parent's override.
    class ChildOfHost(App):
        pass

    assert _class_entity_name(ChildOfHost) == "ChildOfHost"


def test_find_subclass_by_name_routes_by_entity_name():
    # ``App`` (host) matches lookup for "HostApp", not "App".
    assert find_subclass_by_name(Node, "HostApp") is App
    # ``_LibApp`` (the other class also named App in Python) matches "App".
    assert find_subclass_by_name(Node, "App") is _LibApp


@pytest.mark.asyncio
async def test_persisted_entity_field_uses_override(json_context):
    host = App(title="host-side")
    lib = _LibApp(label="lib-side")

    # ``entity`` attribute on the live instance reflects the override at create-time.
    assert host.entity == "HostApp"
    assert lib.entity == "App"

    # ID prefix follows entity name (``n.<entity>.<hex>``).
    assert host.id.startswith("n.HostApp.")
    assert lib.id.startswith("n.App.")

    await json_context.save(host)
    await json_context.save(lib)

    with patch("jvspatial.core.context.get_default_context", return_value=json_context):
        # Cross-class query isolation: each class only sees its own rows.
        hosts = await App.find({})
        libs = await _LibApp.find({})

        assert len(hosts) == 1
        assert len(libs) == 1
        assert hosts[0].id == host.id
        assert libs[0].id == lib.id
        # Deserialization picks the right class for each entity discriminator.
        assert isinstance(hosts[0], App)
        assert isinstance(libs[0], _LibApp)
        assert hosts[0].title == "host-side"
        assert libs[0].label == "lib-side"
