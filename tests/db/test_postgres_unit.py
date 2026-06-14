"""Unit tests for PostgresDB internals that don't require a live DB.

Connection pool auto-tuning, tenant contextvar mechanics, vector
encoding, ``$near`` clause peeling, identifier validation. The
integration tests live in ``test_postgres_integration.py`` and require
``JVSPATIAL_POSTGRES_TEST_DSN`` to be set.
"""

from __future__ import annotations

import asyncio
import os
from typing import Iterator

import pytest

# PostgresDB imports asyncpg at module load; skip the whole module when the
# optional [postgres] extra isn't installed instead of erroring on import.
pytest.importorskip("asyncpg")

from jvspatial.db.postgres import (
    PostgresDB,
    _safe_collection,
    _shift_placeholders,
    current_tenant,
)
from jvspatial.runtime.serverless import (
    is_serverless_mode,
    reset_serverless_mode_cache,
)


# Some tests mutate AWS env vars to flip ``is_serverless_mode``. Restore
# state per-test so we don't leak between cases.
@pytest.fixture(autouse=True)
def _reset_serverless_cache() -> Iterator[None]:
    reset_serverless_mode_cache()
    saved = os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
    yield
    reset_serverless_mode_cache()
    if saved is not None:
        os.environ["AWS_LAMBDA_FUNCTION_NAME"] = saved
    else:
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)


class TestPoolAutoTune:
    def test_non_serverless_defaults(self) -> None:
        db = PostgresDB(dsn="postgresql://nope/none")
        assert db.min_size == 2
        assert db.max_size == 10

    def test_serverless_defaults(self) -> None:
        os.environ["AWS_LAMBDA_FUNCTION_NAME"] = "test"
        reset_serverless_mode_cache()
        assert is_serverless_mode() is True
        db = PostgresDB(dsn="postgresql://nope/none")
        assert db.min_size == 0
        assert db.max_size == 3

    def test_explicit_overrides_win(self) -> None:
        os.environ["AWS_LAMBDA_FUNCTION_NAME"] = "test"
        reset_serverless_mode_cache()
        db = PostgresDB(dsn="postgresql://nope/none", min_size=5, max_size=20)
        assert (db.min_size, db.max_size) == (5, 20)


class TestPoolerMode:
    def test_default_session(self) -> None:
        db = PostgresDB(dsn="postgresql://nope/none")
        assert db.pooler_mode == "session"

    def test_transaction(self) -> None:
        db = PostgresDB(dsn="postgresql://nope/none", pooler_mode="transaction")
        assert db.pooler_mode == "transaction"

    def test_invalid_pooler_mode(self) -> None:
        with pytest.raises(ValueError, match="pooler_mode"):
            PostgresDB(dsn="postgresql://nope/none", pooler_mode="bogus")


class TestIdentifierValidation:
    @pytest.mark.parametrize(
        "name",
        ["user", "_secret", "a", "abc_123", "X1", "node_collection_v2"],
    )
    def test_safe_collection_accepts(self, name: str) -> None:
        assert _safe_collection(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "1user",  # leading digit
            "user-table",  # dash
            "user table",  # space
            "user;DROP",  # injection attempt
            "user.public",  # dot
            "x" * 64,  # 64 chars (max is 63)
            "",  # empty
            "$evil",  # leading dollar
        ],
    )
    def test_safe_collection_rejects(self, name: str) -> None:
        with pytest.raises(ValueError):
            _safe_collection(name)


class TestPlaceholderShift:
    def test_zero_shift_returns_input_unchanged(self) -> None:
        assert _shift_placeholders("a = $1 AND b = $2", shift=0) == "a = $1 AND b = $2"

    def test_positive_shift(self) -> None:
        assert _shift_placeholders("a = $1 AND b = $2", shift=3) == "a = $4 AND b = $5"

    def test_multi_digit_placeholders(self) -> None:
        # Make sure ``$10`` is treated as $10, not $1 + literal '0'.
        assert (
            _shift_placeholders("foo = $10 OR bar = $1", shift=5)
            == "foo = $15 OR bar = $6"
        )


class TestVectorEncoding:
    def test_list_of_floats(self) -> None:
        assert PostgresDB._encode_vector([1.0, 2.0, 3.0]) == "[1.0,2.0,3.0]"

    def test_list_of_ints_promotes_to_float(self) -> None:
        assert PostgresDB._encode_vector([1, 2, 3]) == "[1.0,2.0,3.0]"

    def test_tuple_input(self) -> None:
        assert PostgresDB._encode_vector((0.5, 0.25, 0.125)) == "[0.5,0.25,0.125]"

    def test_rejects_scalar(self) -> None:
        with pytest.raises(TypeError):
            PostgresDB._encode_vector(1.0)

    def test_rejects_string(self) -> None:
        with pytest.raises(TypeError):
            PostgresDB._encode_vector("[1,2,3]")

    def test_rejects_non_numeric_entry(self) -> None:
        with pytest.raises(TypeError):
            PostgresDB._encode_vector([1, "two", 3])


class TestTenantContextVar:
    """Tenant scope mechanics — pure contextvar / async semantics, no DB."""

    @pytest.mark.asyncio
    async def test_no_scope_returns_none(self) -> None:
        assert current_tenant() is None

    @pytest.mark.asyncio
    async def test_scope_sets_tenant(self) -> None:
        db = PostgresDB(dsn="postgresql://nope/none")
        async with db.tenant("acme-42"):
            assert current_tenant() == "acme-42"
        assert current_tenant() is None

    @pytest.mark.asyncio
    async def test_nested_scope_shadows(self) -> None:
        db = PostgresDB(dsn="postgresql://nope/none")
        async with db.tenant("outer"):
            assert current_tenant() == "outer"
            async with db.tenant("inner"):
                assert current_tenant() == "inner"
            assert current_tenant() == "outer"
        assert current_tenant() is None

    @pytest.mark.asyncio
    async def test_sibling_tasks_have_independent_scopes(self) -> None:
        db = PostgresDB(dsn="postgresql://nope/none")
        seen: list = []

        async def worker(tid: str) -> None:
            async with db.tenant(tid):
                # Yield so the scheduler interleaves siblings.
                await asyncio.sleep(0)
                seen.append((tid, current_tenant()))

        await asyncio.gather(worker("alpha"), worker("beta"), worker("gamma"))
        # Each task should see its own tenant, never any other's.
        for tid, observed in seen:
            assert observed == tid

    @pytest.mark.asyncio
    async def test_empty_tenant_rejected(self) -> None:
        db = PostgresDB(dsn="postgresql://nope/none")
        with pytest.raises(ValueError, match="tenant_id"):
            async with db.tenant(""):
                pass


class TestVectorClausePeeling:
    def test_no_vector_columns_passthrough(self) -> None:
        db = PostgresDB(dsn="postgresql://nope/none")
        q = {"context.x": 1, "embedding": {"$near": [1, 2, 3]}}
        out = db._pop_vector_clause("doc", q)
        # No vectors configured → no peel; returns query unchanged.
        assert out[0] == q
        assert out[1] is None

    def test_near_extracted_and_encoded(self) -> None:
        db = PostgresDB(dsn="postgresql://nope/none")
        db._vector_columns["doc"] = {"embedding": 4}
        q = {
            "context.status": "open",
            "embedding": {"$near": [0.1, 0.2, 0.3, 0.4], "$limit": 5},
        }
        filtered, field, vec, lim, ops = db._pop_vector_clause("doc", q)
        # The vector clause is removed from the query body.
        assert filtered == {"context.status": "open"}
        assert field == "embedding"
        assert vec == "[0.1,0.2,0.3,0.4]"
        assert lim == 5
        assert ops == "<=>"

    def test_near_with_other_field_ops_keeps_rest(self) -> None:
        db = PostgresDB(dsn="postgresql://nope/none")
        db._vector_columns["doc"] = {"embedding": 3}
        q = {
            "embedding": {
                "$near": [1, 2, 3],
                "$limit": 10,
                "$exists": True,
            }
        }
        filtered, field, vec, lim, _ = db._pop_vector_clause("doc", q)
        # $exists stays on the field for the regular translator to handle.
        assert filtered == {"embedding": {"$exists": True}}
        assert field == "embedding"
        assert lim == 10

    def test_no_near_in_query_returns_unchanged(self) -> None:
        db = PostgresDB(dsn="postgresql://nope/none")
        db._vector_columns["doc"] = {"embedding": 3}
        q = {"context.x": 1}
        filtered, field, _, _, _ = db._pop_vector_clause("doc", q)
        assert filtered == q
        assert field is None

    def test_malformed_vector_left_to_translator_to_reject(self) -> None:
        """A bad $near value leaves the clause in place so the regular
        translator fails loudly rather than silently dropping it."""
        db = PostgresDB(dsn="postgresql://nope/none")
        db._vector_columns["doc"] = {"embedding": 3}
        q = {"embedding": {"$near": "not a list"}}
        filtered, field, _, _, _ = db._pop_vector_clause("doc", q)
        assert filtered == q  # untouched
        assert field is None
