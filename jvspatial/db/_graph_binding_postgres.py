"""Native one-hop binding summary; policy belongs to the consuming host."""

import json
from typing import Any, Dict, Optional, Tuple

from jvspatial.db.graph_bindings import GraphBindingSummary, LiteralBindingFact


async def summarize(
    database: Any,
    query: Dict[str, Any],
    *,
    record_entity: str,
    edge_entity: str,
    parent_id: str,
    facts: Tuple[LiteralBindingFact, ...],
    max_records: int = 100000,
    max_edges: int = 400000,
) -> Optional[GraphBindingSummary]:
    """Aggregate requested storage facts in one bounded PostgreSQL statement."""
    from jvspatial.db._postgres_translate import translate_query
    from jvspatial.db.postgres import _SAFE_IDENT_RE, _safe_collection

    if (
        not all(
            isinstance(value, str) and value
            for value in (record_entity, edge_entity, parent_id)
        )
        or not isinstance(facts, tuple)
        or not all(isinstance(fact, LiteralBindingFact) for fact in facts)
        or any(
            type(value) is not int or value <= 0 for value in (max_records, max_edges)
        )
    ):
        raise ValueError("Invalid graph binding summary request")
    translated = translate_query(query)
    if translated is None:
        return None
    where, values = translated
    params = list(values)

    def bind(value: Any) -> str:
        params.append(value)
        return f"${len(params)}"

    record_param, edge_param, parent_param = (
        bind(record_entity),
        bind(edge_entity),
        bind(parent_id),
    )
    constraints = [
        "jsonb_typeof(data->'context')='object'",
        "data->'id'=to_jsonb(id)",
        "id<>''",
        f"data->'entity'=to_jsonb({record_param}::text)",
    ]
    for fact in facts:
        paths = [fact.path] + ([fact.legacy_path] if fact.legacy_path else [])
        if any(
            not _SAFE_IDENT_RE.fullmatch(segment)
            for path in paths
            for segment in path.split(".")
        ):
            return None
        canonical = "(data#>'{" + ",".join(fact.path.split(".")) + "}')"
        legacy = (
            ("(data#>'{" + ",".join(fact.legacy_path.split(".")) + "}')")
            if fact.legacy_path
            else None
        )
        chosen = f"COALESCE({canonical},{legacy})" if legacy else canonical
        allowed = bind([json.dumps(value) for value in fact.allowed_values])
        valid = f"({chosen}=ANY({allowed}::jsonb[]))"
        if legacy:
            valid = f"({valid} AND ({canonical} IS NULL OR {legacy} IS NULL OR {canonical}={legacy}))"
        if not fact.required:
            missing = (
                f"({canonical} IS NULL AND {legacy} IS NULL)"
                if legacy
                else f"{canonical} IS NULL"
            )
            valid = f"({missing} OR {valid})"
        constraints.append(valid)
    limit_records = bind(max_records + 1)
    # A record without any link contributes one row. If both budgets hold,
    # their sum bounds the joined rows; hitting the extra row proves overflow.
    joined_budget = max_records + max_edges
    limit_joined = bind(joined_budget + 1)
    schema = _safe_collection(database.schema_name)
    await database._bootstrap_collection("node")
    await database._bootstrap_collection("edge")
    node_where = f"entity={record_param}" + (f" AND ({where})" if where else "")
    sql = f"""
    WITH candidates AS (
      SELECT id, COALESCE({' AND '.join(constraints)},FALSE) AS facts_valid
      FROM {schema}.node WHERE {node_where} LIMIT {limit_records}
    ), bindings AS (
      SELECT c.id, c.facts_valid, e.id IS NOT NULL AS linked,
        e.data->>'source'={parent_param} AS expected,
        COALESCE(jsonb_typeof(e.data->'source')='string' AND e.data->>'source'<>''
          AND jsonb_typeof(e.data->'target')='string'
          AND jsonb_typeof(e.data->'entity')='string'
          AND e.data->>'entity'={edge_param}, FALSE) AS valid
      FROM candidates c LEFT JOIN {schema}.edge e
        ON e.entity={edge_param} AND (e.data#>>'{{target}}')=c.id
      LIMIT {limit_joined}
    ), parents AS (
      SELECT id, facts_valid, count(*) AS joined,
        count(*) FILTER(WHERE linked) AS cardinality,
        bool_and(expected) FILTER(WHERE linked) AS expected,
        bool_or(NOT valid) FILTER(WHERE linked) AS invalid_edge
      FROM bindings GROUP BY id, facts_valid
    )
    SELECT count(*) AS matched,
      count(*) FILTER(WHERE NOT facts_valid) AS invalid_facts,
      count(*) FILTER(WHERE invalid_edge) AS invalid_edges,
      count(*) FILTER(WHERE facts_valid AND NOT invalid_edge AND cardinality=1 AND expected) AS bound,
      COALESCE(sum(cardinality),0) AS edge_count,
      COALESCE(sum(joined),0) AS joined_count
    FROM parents
    """
    async with database._acquire_conn() as connection:
        row = await connection.fetchrow(sql, *params)
    return GraphBindingSummary(
        matched=row["matched"],
        bound=row["bound"],
        invalid_facts=row["invalid_facts"],
        invalid_edges=row["invalid_edges"],
        complete=(
            row["matched"] <= max_records
            and row["edge_count"] <= max_edges
            and row["joined_count"] <= joined_budget
        ),
    )
