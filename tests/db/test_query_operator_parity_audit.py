"""QueryEngine operator parity (audit §5.2 / SPEC §5.1).

The earlier matcher:

* silently returned False for any field-level operator it did not know;
* silently returned False for the top-level ``$nor`` operator the
  QueryBuilder advertised;
* silently passed through optimizer markers (``$hint`` / ``$select``)
  which caused match failures when ``optimize_query`` injected them.

The matcher now raises ``QueryError`` for unsupported operators and
implements ``$nor`` / ``$mod`` / ``$all`` / ``$type`` / ``$not`` so the
QueryBuilder surface and engine behavior line up.
"""

import pytest

from jvspatial.db.query import QueryEngine
from jvspatial.exceptions import QueryError

# ---------- $nor ----------


def test_nor_excludes_documents_matching_any_subcondition():
    doc = {"status": "active", "tier": "free"}
    # Document does NOT match {"status": "inactive"} nor {"tier": "pro"};
    # $nor should accept it.
    assert (
        QueryEngine.match(
            doc,
            {
                "$nor": [
                    {"status": "inactive"},
                    {"tier": "pro"},
                ]
            },
        )
        is True
    )
    # Document DOES match {"status": "active"}; $nor rejects.
    assert QueryEngine.match(doc, {"$nor": [{"status": "active"}]}) is False


# ---------- $mod ----------


def test_mod_matches_remainder():
    assert QueryEngine.match({"n": 10}, {"n": {"$mod": [3, 1]}}) is True
    assert QueryEngine.match({"n": 9}, {"n": {"$mod": [3, 1]}}) is False
    assert QueryEngine.match({"n": "x"}, {"n": {"$mod": [3, 0]}}) is False


# ---------- $all ----------


def test_all_requires_every_operand_in_value():
    assert QueryEngine.match({"tags": ["a", "b", "c"]}, {"tags": {"$all": ["a", "b"]}})
    assert not QueryEngine.match(
        {"tags": ["a", "b", "c"]}, {"tags": {"$all": ["a", "z"]}}
    )
    assert not QueryEngine.match({"tags": "ab"}, {"tags": {"$all": ["a"]}})


# ---------- $type ----------


def test_type_accepts_python_type_names():
    assert QueryEngine.match({"x": 5}, {"x": {"$type": "int"}})
    assert QueryEngine.match({"x": "y"}, {"x": {"$type": "string"}})
    assert not QueryEngine.match({"x": "y"}, {"x": {"$type": "int"}})
    assert not QueryEngine.match({"x": 5}, {"x": {"$type": "bogus"}})


# ---------- $not (field-level) ----------


def test_field_level_not_negates():
    assert QueryEngine.match({"n": 5}, {"n": {"$not": {"$gt": 10}}})
    assert not QueryEngine.match({"n": 5}, {"n": {"$not": {"$gt": 1}}})


# ---------- Unsupported operators raise ----------


def test_unsupported_top_level_operator_raises():
    with pytest.raises(QueryError):
        QueryEngine.match({}, {"$bogus": []})


def test_unsupported_field_level_operator_raises():
    with pytest.raises(QueryError):
        QueryEngine.match({"x": 1}, {"x": {"$bogus": 1}})


# ---------- Optimizer markers are ignored ----------


def test_optimizer_markers_do_not_break_match():
    """``$hint`` / ``$select`` are optimizer-only — match() must skip them."""
    doc = {"name": "alice"}
    # With $hint mixed in, the match still passes on the actual condition.
    assert QueryEngine.match(doc, {"name": "alice", "$hint": "name_idx"})
    assert QueryEngine.match(doc, {"$select": ["name"]})
