"""Decorator indexes must use the same record paths as find/sort."""

from jvspatial.core import Node, Object
from jvspatial.core.annotations import compound_index


@compound_index([("title", 1), ("id", -1), ("entity", 1)], name="identity_tiebreaker")
class IdentityIndexedNode(Node):
    title: str = ""


@compound_index([("id", 1)], name="object_identity")
class IdentityIndexedObject(Object):
    pass


def test_node_compound_identity_fields_are_not_nested():
    index = next(
        row
        for row in IdentityIndexedNode.get_indexes()
        if row.get("name") == "identity_tiebreaker"
    )
    assert index["fields"] == [("context.title", 1), ("id", -1), ("entity", 1)]


def test_object_compound_identity_field_is_rooted():
    index = next(
        row
        for row in IdentityIndexedObject.get_indexes()
        if row.get("name") == "object_identity"
    )
    assert index["fields"] == [("id", 1)]
