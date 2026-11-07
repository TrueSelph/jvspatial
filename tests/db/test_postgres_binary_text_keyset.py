"""Explicit text keysets preserve portable ordering under PostgreSQL collation."""

import pytest

from tests.db.test_postgres_integration import pg_db as pg_db

pytestmark = pytest.mark.asyncio
KEY = {"field": "context.label", "scope_field": "context.parent", "entity": "Record"}


@pytest.mark.parametrize("direction", [1, -1])
async def test_binary_keyset_orders_unicode_ties_and_missing_last(pg_db, direction):
    await pg_db.create_binary_text_keyset_indexes("node", **KEY)
    labels = ["a", "Z", "Z", "é", "Ω", "😀", None, "", None]
    expected = []
    for i, label in enumerate(labels):
        identifier = f"n.Record.{i}"
        context = {"parent": "wanted"}
        if i != 8:
            context["label"] = label
        await pg_db.save(
            "node", {"id": identifier, "entity": "Record", "context": context}
        )
        expected.append((label, identifier))
    await pg_db.save(
        "node",
        {
            "id": "n.Record.foreign",
            "entity": "Record",
            "context": {"parent": "foreign", "label": 123},
        },
    )
    reverse = direction == -1
    present = sorted(
        (item for item in expected if item[0] is not None), reverse=reverse
    )
    missing = sorted((item for item in expected if item[0] is None), reverse=reverse)
    seen = []
    cursor = None
    for _ in range(6):
        rows = await pg_db.find_binary_text_keyset(
            "node",
            {},
            **KEY,
            scope_value="wanted",
            direction=direction,
            after=cursor,
            limit=2,
        )
        if not rows:
            break
        seen.extend((row["context"].get("label"), row["id"]) for row in rows)
        cursor = seen[-1]
    assert seen == present + missing


@pytest.mark.parametrize("bad_value", [42, "😀" * 400])
async def test_binary_keyset_falls_back_for_out_of_contract_values(pg_db, bad_value):
    await pg_db.create_binary_text_keyset_indexes("node", **KEY)
    await pg_db.save(
        "node",
        {
            "id": "n.Record.unsupported",
            "entity": "Record",
            "context": {"parent": "wanted", "label": bad_value},
        },
    )
    assert (
        await pg_db.find_binary_text_keyset(
            "node", {}, **KEY, scope_value="wanted", direction=1, after=None, limit=2
        )
        is None
    )
