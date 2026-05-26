"""Unit tests for the Postgres JSONB query translator.

Pure-Python tests — no DB required. Verifies that every operator the
plan promises to push down produces a coherent SQL fragment with bound
parameters, and that ``$where`` / ``$text`` correctly fall back so the
caller can drop to in-Python ``QueryEngine``.
"""

from __future__ import annotations

import pytest

from jvspatial.db._postgres_translate import (
    ParamBuilder,
    translate_query,
    translate_sort,
)


class TestParamBuilder:
    """Placeholder allocator behaves like asyncpg expects."""

    def test_sequential_placeholders(self) -> None:
        pb = ParamBuilder()
        assert pb.add("a") == "$1"
        assert pb.add(2) == "$2"
        assert pb.add(True) == "$3"
        assert pb.values == ["a", 2, True]


class TestEqualityAndComparators:
    def test_plain_equality_string(self) -> None:
        sql, params = translate_query({"context.name": "alpha"})
        assert sql == "(data #>> '{context,name}') = $1"
        assert params == ["alpha"]

    def test_plain_equality_number(self) -> None:
        sql, params = translate_query({"context.age": 30})
        assert "::numeric" in sql
        assert params == [30]

    def test_plain_equality_bool(self) -> None:
        sql, params = translate_query({"context.active": True})
        assert "to_jsonb" in sql and "::boolean" in sql
        assert params == [True]

    def test_plain_equality_null(self) -> None:
        sql, params = translate_query({"context.deleted_at": None})
        assert "IS NULL" in sql
        assert params == []

    def test_range_pushdown(self) -> None:
        sql, params = translate_query({"context.age": {"$gte": 18, "$lt": 65}})
        assert ">=" in sql and "<" in sql
        assert params == [18, 65]

    def test_ne_includes_null_check(self) -> None:
        sql, params = translate_query({"context.x": {"$ne": "abc"}})
        # $ne treats NULL as "not equal" per QueryEngine semantics.
        assert "IS NULL OR NOT" in sql
        assert params == ["abc"]


class TestInOperators:
    def test_in_strings(self) -> None:
        sql, params = translate_query({"context.tag": {"$in": ["a", "b", "c"]}})
        assert "ANY($1::text[])" in sql
        assert params == [["a", "b", "c"]]

    def test_in_numbers(self) -> None:
        sql, params = translate_query({"context.age": {"$in": [18, 21, 30]}})
        assert "::numeric[]" in sql

    def test_empty_in_matches_nothing(self) -> None:
        sql, _ = translate_query({"context.tag": {"$in": []}})
        assert sql.strip() == "FALSE"

    def test_nin_strings(self) -> None:
        sql, params = translate_query({"context.tag": {"$nin": ["x"]}})
        # Should treat NULL as "not in the list".
        assert "IS NULL OR NOT" in sql
        assert params == [["x"]]

    def test_empty_nin_matches_everything(self) -> None:
        sql, _ = translate_query({"context.tag": {"$nin": []}})
        assert sql.strip() == "TRUE"


class TestExistenceAndType:
    def test_exists_true(self) -> None:
        sql, _ = translate_query({"context.x": {"$exists": True}})
        assert sql.endswith("IS NOT NULL")

    def test_exists_false(self) -> None:
        sql, _ = translate_query({"context.x": {"$exists": False}})
        assert sql.endswith("IS NULL")

    def test_type_string(self) -> None:
        sql, params = translate_query({"context.x": {"$type": "string"}})
        assert "jsonb_typeof" in sql
        assert params == ["string"]

    def test_type_int_aliases_number(self) -> None:
        sql, params = translate_query({"context.x": {"$type": "int"}})
        assert params == ["number"]

    def test_type_unknown_falls_back(self) -> None:
        # Mongo BSON-specific aliases we don't translate -> fallback.
        result = translate_query({"context.x": {"$type": "decimal128"}})
        assert result is None


class TestRegexAndMod:
    def test_regex_case_sensitive(self) -> None:
        sql, params = translate_query({"context.email": {"$regex": "@example\\."}})
        assert " ~ $1" in sql and "~*" not in sql
        assert params == ["@example\\."]

    def test_regex_case_insensitive(self) -> None:
        sql, params = translate_query(
            {"context.email": {"$regex": "v75", "$options": "i"}}
        )
        assert "~*" in sql

    def test_regex_unsupported_flag_falls_back(self) -> None:
        # We honor 'i' only; 'm'/'s'/'x' fall back to be safe.
        assert translate_query({"context.x": {"$regex": "a", "$options": "im"}}) is None

    def test_mod(self) -> None:
        sql, params = translate_query({"context.value": {"$mod": [10, 0]}})
        assert "%" in sql
        assert params == [10.0, 0.0]


class TestArrayOperators:
    def test_size(self) -> None:
        sql, params = translate_query({"context.scores": {"$size": 3}})
        assert "jsonb_array_length" in sql
        assert params == [3]

    def test_all(self) -> None:
        sql, params = translate_query({"context.scores": {"$all": [1, 2]}})
        assert "@> $1::jsonb" in sql and "@> $2::jsonb" in sql

    def test_elem_match_with_nested_predicates(self) -> None:
        sql, params = translate_query(
            {
                "context.entries": {
                    "$elemMatch": {
                        "status": "open",
                        "count": {"$gt": 5},
                    }
                }
            }
        )
        assert "EXISTS (SELECT 1 FROM jsonb_array_elements" in sql
        assert "elem #>> '{status}'" in sql
        assert "elem #>> '{count}'" in sql
        # Two params: 'open' for status, 5 for count.
        assert params == ["open", 5]


class TestLogicalOperators:
    def test_and(self) -> None:
        sql, params = translate_query(
            {"$and": [{"context.x": 1}, {"context.y": {"$lt": 5}}]}
        )
        assert " AND " in sql
        assert params == [1, 5]

    def test_or(self) -> None:
        sql, params = translate_query({"$or": [{"context.a": "x"}, {"context.b": "y"}]})
        assert " OR " in sql
        assert params == ["x", "y"]

    def test_nor(self) -> None:
        sql, params = translate_query({"$nor": [{"context.bad": True}]})
        assert sql.strip().startswith("(NOT")
        assert params == [True]

    def test_not_field_level(self) -> None:
        sql, _ = translate_query({"context.flag": {"$not": {"$eq": True}}})
        assert sql.startswith("NOT (")


class TestFallback:
    def test_where_falls_back(self) -> None:
        assert translate_query({"context.x": {"$where": "function() {}"}}) is None

    def test_text_falls_back(self) -> None:
        assert translate_query({"context.x": {"$text": {"$search": "foo"}}}) is None

    def test_unknown_top_level_op_falls_back(self) -> None:
        assert translate_query({"$totallyMadeUp": {}}) is None

    def test_unsafe_field_path_falls_back(self) -> None:
        # Dollar-sign in field name → fallback (we never interpolate it).
        assert translate_query({"context.$evil": "x"}) is None
        # Spaces / slashes / brackets also rejected.
        assert translate_query({"context.with space": "x"}) is None
        assert translate_query({"context.has/slash": "x"}) is None


class TestSort:
    def test_simple_ascending(self) -> None:
        assert (
            translate_sort([("context.score", 1)])
            == "(data #>> '{context,score}') ASC NULLS LAST"
        )

    def test_simple_descending(self) -> None:
        assert (
            translate_sort([("context.score", -1)])
            == "(data #>> '{context,score}') DESC NULLS LAST"
        )

    def test_compound(self) -> None:
        out = translate_sort([("a", 1), ("b", -1)])
        assert (
            out == "(data #>> '{a}') ASC NULLS LAST, (data #>> '{b}') DESC NULLS LAST"
        )

    def test_invalid_direction(self) -> None:
        assert translate_sort([("x", 2)]) is None

    def test_unsafe_field(self) -> None:
        assert translate_sort([("$bad", 1)]) is None
