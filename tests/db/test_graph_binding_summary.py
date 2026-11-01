"""Storage facts cannot hide malformed literals, extra parents or truncation."""

import pytest

from jvspatial.db.graph_bindings import GraphBindingSummary, LiteralBindingFact
from tests.db.test_postgres_integration import pg_db as pg_db

pytestmark = pytest.mark.asyncio
FACTS = (
    LiteralBindingFact("context.parent_key", ("root",), "parent_key"),
    LiteralBindingFact("context.state", ("ready", "hold"), "state"),
)


async def seed(db, *, context=None, **legacy):
    record = {
        "id": "record",
        "entity": "Record",
        "context": (
            context if context is not None else {"parent_key": "root", "state": "ready"}
        ),
        **legacy,
    }
    await db.save("node", record)
    await db.save(
        "edge",
        {
            "id": "link",
            "entity": "Relation",
            "source": "root",
            "target": "record",
            "context": {},
        },
    )
    return record


async def summary(db, **kwargs):
    return await db.summarize_graph_bindings(
        {},
        record_entity="Record",
        edge_entity="Relation",
        parent_id="root",
        facts=FACTS,
        **kwargs,
    )


async def test_exact_summary_and_foreign_entity_isolation(pg_db):
    await seed(pg_db)
    await pg_db.save("node", {"id": "foreign", "entity": "Other", "context": {}})
    assert await summary(pg_db) == GraphBindingSummary(1, 1, 0, 0, True)


@pytest.mark.parametrize("damage", ["missing", "extra", "wrong"])
async def test_noncanonical_parent_does_not_count(pg_db, damage):
    await seed(pg_db)
    if damage == "missing":
        await pg_db.delete("edge", "link")
    elif damage == "extra":
        await pg_db.save(
            "edge",
            {
                "id": "extra",
                "entity": "Relation",
                "source": "other",
                "target": "record",
            },
        )
    else:
        await pg_db.save(
            "edge",
            {"id": "link", "entity": "Relation", "source": "other", "target": "record"},
        )
    assert await summary(pg_db) == GraphBindingSummary(1, 0, 0, 0, True)


@pytest.mark.parametrize("value", [None, 1, [], "unknown"])
async def test_invalid_literal_is_reported(pg_db, value):
    await seed(pg_db, context={"parent_key": "root", "state": value})
    assert (await summary(pg_db)).invalid_facts == 1


async def test_legacy_value_and_explicit_null_remain_distinct(pg_db):
    record = await seed(pg_db, context={"parent_key": "root"}, state="ready")
    assert (await summary(pg_db)).bound == 1
    record["context"]["state"] = None
    await pg_db.save("node", record)
    assert (await summary(pg_db)).invalid_facts == 1
    record["context"]["state"] = "hold"
    await pg_db.save("node", record)
    assert (await summary(pg_db)).invalid_facts == 1


@pytest.mark.parametrize("source", [None, "", [], 1])
async def test_malformed_edge_remains_explicit(pg_db, source):
    await seed(pg_db)
    await pg_db.save(
        "edge",
        {"id": "link", "entity": "Relation", "source": source, "target": "record"},
    )
    assert (await summary(pg_db)).invalid_edges == 1


async def test_limit_is_incomplete_not_an_exact_partial_total(pg_db):
    await seed(pg_db)
    await pg_db.save(
        "node",
        {
            "id": "second",
            "entity": "Record",
            "context": {"parent_key": "root", "state": "ready"},
        },
    )
    assert not (await summary(pg_db, max_records=1)).complete
    assert (await summary(pg_db, max_edges=1)).complete

    await pg_db.save(
        "edge",
        {"id": "extra", "entity": "Relation", "source": "other", "target": "record"},
    )
    assert not (await summary(pg_db, max_edges=1)).complete


async def test_unsafe_path_and_unsupported_query_fall_back(pg_db):
    assert (
        await pg_db.summarize_graph_bindings(
            {},
            record_entity="Record",
            edge_entity="Relation",
            parent_id="root",
            facts=(LiteralBindingFact("context.x'); DROP TABLE node;--", ("x",)),),
        )
        is None
    )
    assert (
        await pg_db.summarize_graph_bindings(
            {"context.value": {"$unsupported": 1}},
            record_entity="Record",
            edge_entity="Relation",
            parent_id="root",
            facts=FACTS,
        )
        is None
    )


async def test_query_proof_never_hides_legacy_conflict(pg_db):
    await seed(pg_db, parent_key=None)
    result = await pg_db.summarize_graph_bindings(
        {"context.parent_key": "root"},
        record_entity="Record",
        edge_entity="Relation",
        parent_id="root",
        facts=FACTS,
    )
    assert result.invalid_facts == 1


async def test_text_in_coercion_does_not_prove_literal_type(pg_db):
    await seed(pg_db, context={"parent_key": 123, "state": "ready"})
    result = await pg_db.summarize_graph_bindings(
        {"context.parent_key": {"$in": ["123"]}},
        record_entity="Record",
        edge_entity="Relation",
        parent_id="root",
        facts=(LiteralBindingFact("context.parent_key", ("123",)),),
    )
    assert result.matched == 1 and result.invalid_facts == 1
