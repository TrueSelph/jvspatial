"""PostgreSQL keyset ordering with the same text order as Python."""

import hashlib
import json

from ._postgres_translate import _path_literal, _safe_field_path, translate_query


def _expressions(field, scope_field):
    if not all(_safe_field_path(path) for path in (field, scope_field)):
        raise ValueError("Invalid text keyset field path")
    value = f"(data #> '{_path_literal(field)}')"
    title = f"(data #>> '{_path_literal(field)}') COLLATE \"C\""
    scope = f"(data #> '{_path_literal(scope_field)}')"
    # Keep unusually long legacy values out of the B-tree without blocking
    # writes or silently changing how the caller sorts them.
    malformed = (
        f"(COALESCE(jsonb_typeof({value}) NOT IN ('string','null'), FALSE) "
        f"OR COALESCE(octet_length({title}) > 1024, FALSE))"
    )
    return title, scope, malformed


async def create_indexes(database, collection, *, field, scope_field, entity):
    """Create the scoped text and fallback-detection indexes."""
    from .postgres import _pg_string_literal, _safe_collection

    title, scope, malformed = _expressions(field, scope_field)
    schema, table = _safe_collection(database.schema_name), _safe_collection(collection)
    key = hashlib.sha256(
        f"{table}:{entity}:{scope_field}:{field}".encode()
    ).hexdigest()[:24]
    entity_filter = f"entity={_pg_string_literal(entity)}"
    await database._bootstrap_collection(collection)
    async with database._acquire_conn() as connection:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
                schema,
                key,
            )
            for direction in ("ASC", "DESC"):
                await connection.execute(
                    f"CREATE INDEX IF NOT EXISTS text_page_{key}_{direction.lower()} "
                    f"ON {schema}.{table} "
                    f"({scope}, {title} {direction} NULLS LAST, "
                    f'id COLLATE "C" {direction}) WHERE {entity_filter} AND NOT {malformed}'
                )
            await connection.execute(
                f"CREATE INDEX IF NOT EXISTS text_page_{key}_malformed "
                f"ON {schema}.{table} ({scope}) WHERE {entity_filter} AND {malformed}"
            )


async def read_page(
    database,
    collection,
    query,
    *,
    field,
    scope_field,
    scope_value,
    entity,
    direction,
    after,
    limit,
):
    """Read a binary-ordered page or signal portable fallback."""
    from .postgres import _pg_string_literal, _safe_collection

    if (
        direction not in (1, -1)
        or type(limit) is not int
        or limit <= 0
        or not isinstance(scope_value, str)
        or not isinstance(entity, str)
        or (
            after is not None
            and (
                not isinstance(after, tuple)
                or len(after) != 2
                or (after[0] is not None and not isinstance(after[0], str))
                or not isinstance(after[1], str)
            )
        )
    ):
        raise ValueError("Invalid binary text keyset request")
    translated = translate_query(query)
    if translated is None:
        return None
    title, scope, malformed = _expressions(field, scope_field)
    schema, table = _safe_collection(database.schema_name), _safe_collection(collection)
    predicate, values = translated
    params = list(values)

    def bind(value):
        params.append(value)
        return f"${len(params)}"

    scope_where = f"entity={_pg_string_literal(entity)} AND {scope}=to_jsonb({bind(scope_value)}::text)"
    where = f"{scope_where} AND ({predicate})" if predicate else scope_where
    # Check the whole scope, including rows outside the caller's filter. A
    # malformed title must never silently change the portable ordering.
    invalid = f"SELECT 1 FROM {schema}.{table} WHERE {scope_where} AND {malformed}"
    order = "ASC" if direction == 1 else "DESC"
    op = ">" if direction == 1 else "<"
    identifier = 'id COLLATE "C"'
    order_by = f"{title} {order} NULLS LAST, {identifier} {order}"
    where += f" AND NOT {malformed}"
    where += " AND current_setting('server_encoding')='UTF8' AND NOT EXISTS (SELECT 1 FROM invalid)"
    select = f"SELECT data, id FROM {schema}.{table} WHERE {where}"
    cap = bind(limit)
    if after is None:
        page = f"SELECT data FROM {schema}.{table} WHERE {where} ORDER BY {order_by} LIMIT {cap}"
    else:
        value, record_id = after
        tie = bind(record_id)
        if value is None:
            page = (
                f"SELECT data FROM {schema}.{table} WHERE {where} AND {title} IS NULL "
                f"AND {identifier} {op} {tie} ORDER BY {order_by} LIMIT {cap}"
            )
        else:
            cursor = bind(value)
            # Separate the null tail so the non-null branch can seek directly
            # on the composite (text, ID) key, including on deep cursors.
            page = (
                f"SELECT data FROM (({select} AND ({title}, {identifier}) {op} "
                f"({cursor}, {tie}) ORDER BY {order_by} LIMIT {cap}) UNION ALL "
                f"({select} AND {title} IS NULL ORDER BY {order_by} LIMIT {cap})) "
                f"AS page ORDER BY {order_by} LIMIT {cap}"
            )
    statement = (
        f"WITH invalid AS MATERIALIZED ({invalid} LIMIT 1) "
        f"SELECT (current_setting('server_encoding')<>'UTF8' OR EXISTS (SELECT 1 FROM invalid)) AS invalid, ARRAY({page}) AS rows"
    )
    await database._bootstrap_collection(collection)
    async with database._acquire_conn() as connection:
        row = await connection.fetchrow(statement, *params)
    if row["invalid"]:
        return None
    return [json.loads(item) if isinstance(item, str) else item for item in row["rows"]]
