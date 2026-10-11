"""QueryEngine.apply_update — Mongo-style update operators applied in Python.

Backends without native update operators (Postgres ``find_one_and_update``,
JsonDB / SQLite / DynamoDB defaults) rely on this, so every operator the
library emits must be honored rather than silently skipped.
"""

from jvspatial.db.query import QueryEngine


def test_add_to_set_and_pull_round_trip():
    doc = {"id": "n.X.1", "edges": ["e.1"]}
    QueryEngine.apply_update(doc, {"$addToSet": {"edges": "e.2"}})
    QueryEngine.apply_update(doc, {"$addToSet": {"edges": "e.2"}})
    assert doc["edges"] == ["e.1", "e.2"]

    QueryEngine.apply_update(doc, {"$pull": {"edges": "e.1"}})
    assert doc["edges"] == ["e.2"]


def test_pull_removes_every_match_and_ignores_missing_field():
    doc = {"tags": ["a", "b", "a"], "context": {"n": [1, 2, 1]}}
    QueryEngine.apply_update(doc, {"$pull": {"tags": "a", "context.n": 1}})
    assert doc["tags"] == ["b"]
    assert doc["context"]["n"] == [2]

    QueryEngine.apply_update(doc, {"$pull": {"absent": "x"}})
    assert "absent" not in doc
