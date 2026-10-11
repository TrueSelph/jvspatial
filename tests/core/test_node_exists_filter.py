"""Local node criteria retain the in-memory matcher's null/absence contract."""

from typing import Any

import pytest

from jvspatial import Node
from jvspatial.db.query import QueryEngine


class ExistsFilterNode(Node):
    value: Any = None


@pytest.mark.parametrize("value", [None, False, 0, "", [], {}, "present"])
@pytest.mark.parametrize("exists", [True, False])
def test_node_exists_matches_in_memory_contract(value, exists):
    node = ExistsFilterNode(value=value)
    criteria = {"$exists": exists}
    expected = QueryEngine.match({"value": value}, {"value": criteria})
    assert node._matches_property_filter(node, {"context.value": criteria}) == expected


@pytest.mark.parametrize("exists", [True, False])
def test_undeclared_node_field_counts_as_absent(exists):
    node = ExistsFilterNode()
    assert node._matches_property_filter(
        node, {"context.undeclared": {"$exists": exists}}
    ) == (not exists)
