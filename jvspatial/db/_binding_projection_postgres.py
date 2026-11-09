"""Opt-in PostgreSQL storage for one exact graph-binding projection.

A projection belongs to one schema and one query shape. Installation is an
explicit maintenance operation. PostgreSQL commits the backfill and triggers
together before a reader can use the projection.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

from .graph_bindings import GraphBindingSummary, LiteralBindingFact

_CONFIG = "jvspatial_binding_projection_config_v1"
_ROWS = "jvspatial_binding_projection_rows_v1"


@dataclass(frozen=True)
class BindingProjection:
    """One exact candidate partition and its persisted fact constraints."""

    partition_path: str
    record_entity: str
    edge_entity: str
    parent_id: str
    facts: Tuple[LiteralBindingFact, ...]

    def __post_init__(self) -> None:
        """Validate the partition and binding facts before generating SQL."""
        from .postgres import _SAFE_IDENT_RE

        if (
            not isinstance(self.partition_path, str)
            or not self.partition_path.startswith("context.")
            or any(
                not _SAFE_IDENT_RE.fullmatch(part)
                for part in self.partition_path.split(".")
            )
            or not all(
                type(value) is str and value
                for value in (self.record_entity, self.edge_entity, self.parent_id)
            )
            or not isinstance(self.facts, tuple)
            or not all(
                isinstance(fact, LiteralBindingFact)
                and all(
                    _SAFE_IDENT_RE.fullmatch(part)
                    for path in (fact.path, fact.legacy_path)
                    if path is not None
                    for part in path.split(".")
                )
                for fact in self.facts
            )
        ):
            raise ValueError("Invalid graph binding projection configuration")

    def excluded_ids(self, query: Dict[str, Any]) -> Optional[Tuple[str, ...]]:
        """Recognize an exact partition with optional bounded ID exclusions."""
        pending = [query]
        partition_seen = False
        excluded: set[str] = set()
        while pending:
            clause = pending.pop()
            if not isinstance(clause, dict) or not clause:
                return None
            for key, value in clause.items():
                if key == "$and" and isinstance(value, list) and value:
                    pending.extend(value)
                elif key == self.partition_path and value == self.parent_id:
                    partition_seen = True
                elif key == "id" and isinstance(value, dict) and set(value) == {"$nin"}:
                    ids = value["$nin"]
                    if (
                        not isinstance(ids, (list, tuple))
                        or len(ids) > 4096
                        or not all(isinstance(entry_id, str) for entry_id in ids)
                    ):
                        return None
                    excluded.update(ids)
                    if len(excluded) > 4096:
                        return None
                elif key != "entity" or value != self.record_entity:
                    return None
        return tuple(sorted(excluded)) if partition_seen else None

    def configuration(self) -> str:
        """Encode a deterministic configuration for transactional comparison."""
        config = asdict(self)
        config["partition_path"] = self.partition_path.split(".")
        config["facts"] = [
            {
                "path": fact.path.split("."),
                "legacy": fact.legacy_path.split(".") if fact.legacy_path else None,
                "allowed": fact.allowed_values,
                "required": fact.required,
            }
            for fact in self.facts
        ]
        return json.dumps(config, sort_keys=True)


def _scope_sql(schema: str) -> str:
    # A global projection may never substitute for a role-filtered raw read.
    # Check the catalog in the statement that reads the derived rows.
    return f"""NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_class
        WHERE oid IN ('{schema}.node'::regclass, '{schema}.edge'::regclass)
          AND relrowsecurity
    ) AND has_table_privilege('{schema}.node', 'SELECT')
      AND has_table_privilege('{schema}.edge', 'SELECT')"""


def _trigger_signature(schema: str) -> str:
    # Catalog tuple revisions change when a trigger is disabled and enabled.
    # A matching name alone would allow an unmaintained projection back online.
    return f"""(
        SELECT CASE WHEN count(*)=4 THEN
            string_agg(oid::text || ':' || xmin::text, ',' ORDER BY oid)
        END
        FROM pg_catalog.pg_trigger
        WHERE tgrelid IN ('{schema}.node'::regclass, '{schema}.edge'::regclass)
          AND tgenabled='A'
          AND (tgname,tgfoid) IN (
            ('jvspatial_binding_maintain_v1',
                to_regprocedure('{schema}.jvspatial_binding_maintain_v1()')),
            ('jvspatial_binding_invalidate_v1',
                to_regprocedure('{schema}.jvspatial_binding_invalidate_v1()'))
          )
    )"""


def _ddl(schema: str) -> str:
    config = f"{schema}.{_CONFIG}"
    rows = f"{schema}.{_ROWS}"
    return f"""
    CREATE TABLE IF NOT EXISTS {config} (
        singleton boolean PRIMARY KEY CHECK (singleton),
        shape jsonb NOT NULL,
        ready boolean NOT NULL,
        trigger_signature text
    );
    CREATE TABLE IF NOT EXISTS {rows} (
        id text PRIMARY KEY,
        facts_valid boolean NOT NULL,
        invalid_edge boolean NOT NULL,
        cardinality bigint NOT NULL,
        expected boolean NOT NULL
    );
    CREATE OR REPLACE FUNCTION {schema}.jvspatial_binding_node_facts_v1(
        node_id text, data jsonb, shape jsonb
    ) RETURNS jsonb LANGUAGE sql IMMUTABLE SET search_path = pg_catalog AS $$
        SELECT jsonb_build_array(
            jsonb_typeof(data->'context'), data->'id', data->'entity',
            data #> ARRAY(SELECT jsonb_array_elements_text(shape->'partition_path')),
            COALESCE((
                SELECT jsonb_agg(
                    jsonb_build_array(canonical IS NOT NULL, canonical,
                        legacy IS NOT NULL, legacy) ORDER BY ordinality
                )
                FROM jsonb_array_elements(shape->'facts') WITH ORDINALITY AS fs(f, ordinality)
                CROSS JOIN LATERAL (
                    SELECT data #> ARRAY(SELECT jsonb_array_elements_text(f->'path')) AS canonical,
                        CASE WHEN jsonb_typeof(f->'legacy')='array' THEN
                            data #> ARRAY(SELECT jsonb_array_elements_text(f->'legacy'))
                        END AS legacy
                ) values_at_path
            ), '[]'::jsonb), node_id
        )
    $$;
    CREATE OR REPLACE FUNCTION {schema}.jvspatial_binding_facts_valid_v1(
        node_id text, data jsonb, shape jsonb
    ) RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog AS $$
        SELECT COALESCE(
            jsonb_typeof(data->'context')='object' AND data->'id'=to_jsonb(node_id)
            AND node_id<>'' AND data->'entity'=shape->'record_entity'
            AND NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements(shape->'facts') AS facts(f)
                CROSS JOIN LATERAL (
                    SELECT data #> ARRAY(SELECT jsonb_array_elements_text(f->'path')) AS canonical,
                        CASE WHEN jsonb_typeof(f->'legacy')='array' THEN
                            data #> ARRAY(SELECT jsonb_array_elements_text(f->'legacy'))
                        END AS legacy
                ) values_at_path
                WHERE NOT COALESCE(
                    (canonical IS NULL AND legacy IS NULL AND NOT (f->>'required')::boolean)
                    OR (f->'allowed' @> jsonb_build_array(COALESCE(canonical,legacy))
                        AND (canonical IS NULL OR legacy IS NULL OR canonical=legacy)),
                    FALSE
                )
            ), FALSE)
    $$;
    CREATE OR REPLACE FUNCTION {schema}.jvspatial_binding_edge_valid_v1(
        data jsonb, edge_entity text
    ) RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = pg_catalog AS $$
        SELECT COALESCE(jsonb_typeof(data->'source')='string'
            AND data->>'source'<>''
            AND jsonb_typeof(data->'target')='string'
            AND jsonb_typeof(data->'entity')='string'
            AND data->>'entity'=edge_entity, FALSE)
    $$;
    CREATE OR REPLACE FUNCTION {schema}.jvspatial_binding_refresh_v1(
        target_id text, shape jsonb
    ) RETURNS void LANGUAGE plpgsql VOLATILE SET search_path = pg_catalog AS $$
    BEGIN
        PERFORM pg_advisory_xact_lock(hashtext('{schema}.{_ROWS}'), hashtext(target_id));
        INSERT INTO {rows} (id, facts_valid, invalid_edge, cardinality, expected)
        SELECT n.id, {schema}.jvspatial_binding_facts_valid_v1(n.id,n.data,shape),
            COALESCE(e.invalid_edge,FALSE), e.cardinality, COALESCE(e.expected,FALSE)
        FROM {schema}.node n
        CROSS JOIN LATERAL (
            SELECT count(*) AS cardinality,
                bool_and(data->>'source'=shape->>'parent_id') AS expected,
                bool_or(NOT {schema}.jvspatial_binding_edge_valid_v1(
                    data, shape->>'edge_entity')) AS invalid_edge
            FROM {schema}.edge
            WHERE entity=shape->>'edge_entity' AND (data #>> '{{target}}')=target_id
        ) e
        WHERE n.id=target_id AND n.entity=shape->>'record_entity'
            AND n.data #> ARRAY(SELECT jsonb_array_elements_text(shape->'partition_path'))
                =shape->'parent_id'
        ON CONFLICT (id) DO UPDATE SET facts_valid=EXCLUDED.facts_valid,
            invalid_edge=EXCLUDED.invalid_edge, cardinality=EXCLUDED.cardinality,
            expected=EXCLUDED.expected;
        IF NOT FOUND THEN
            DELETE FROM {rows} WHERE id=target_id;
        END IF;
    END
    $$;
    CREATE OR REPLACE FUNCTION {schema}.jvspatial_binding_maintain_v1()
    RETURNS trigger LANGUAGE plpgsql VOLATILE SET search_path = pg_catalog AS $$
    DECLARE
        shape jsonb;
        old_target text;
        new_target text;
        target text;
    BEGIN
        -- A transaction with an older fixed snapshot cannot safely refresh
        -- facts after waiting for another writer. Invalidate in its transaction
        -- or force a retry if publication is newer than its snapshot.
        IF current_setting('transaction_isolation')<>'read committed' THEN
            UPDATE {config} SET ready=false WHERE singleton;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'binding projection publication is newer than this snapshot'
                    USING ERRCODE='serialization_failure';
            END IF;
            RETURN NULL;
        END IF;
        SELECT c.shape INTO shape FROM {config} c WHERE singleton AND ready;
        IF shape IS NULL THEN RETURN NULL; END IF;
        IF NOT ({_scope_sql(schema)}) THEN
            UPDATE {config} SET ready=false WHERE singleton;
            RETURN NULL;
        END IF;
        IF TG_TABLE_NAME='node' THEN
            IF TG_OP='UPDATE' AND OLD.entity=NEW.entity AND
                {schema}.jvspatial_binding_node_facts_v1(OLD.id,OLD.data,shape)
                IS NOT DISTINCT FROM
                {schema}.jvspatial_binding_node_facts_v1(NEW.id,NEW.data,shape)
            THEN RETURN NULL; END IF;
            IF TG_OP<>'INSERT' AND OLD.entity=shape->>'record_entity'
                THEN old_target=OLD.id; END IF;
            IF TG_OP<>'DELETE' AND NEW.entity=shape->>'record_entity'
                THEN new_target=NEW.id; END IF;
        ELSE
            IF TG_OP='UPDATE' AND ROW(OLD.entity,OLD.data->'entity',OLD.data->'source',OLD.data->'target')
                IS NOT DISTINCT FROM ROW(NEW.entity,NEW.data->'entity',NEW.data->'source',NEW.data->'target')
            THEN RETURN NULL; END IF;
            IF TG_OP<>'INSERT' AND OLD.entity=shape->>'edge_entity'
                THEN old_target=OLD.data #>> '{{target}}'; END IF;
            IF TG_OP<>'DELETE' AND NEW.entity=shape->>'edge_entity'
                THEN new_target=NEW.data #>> '{{target}}'; END IF;
        END IF;
        FOR target IN SELECT DISTINCT id FROM unnest(ARRAY[old_target,new_target]) t(id)
            WHERE id IS NOT NULL ORDER BY id LOOP
            PERFORM {schema}.jvspatial_binding_refresh_v1(target,shape);
        END LOOP;
        RETURN NULL;
    END
    $$;
    CREATE OR REPLACE FUNCTION {schema}.jvspatial_binding_invalidate_v1()
    RETURNS trigger LANGUAGE plpgsql VOLATILE SET search_path = pg_catalog AS $$
    BEGIN
        UPDATE {config} SET ready=false WHERE singleton;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'binding projection publication is newer than this snapshot'
                USING ERRCODE='serialization_failure';
        END IF;
        RETURN NULL;
    END
    $$;
    """


async def install(database: Any, projection: BindingProjection) -> None:
    """Backfill and publish atomically while holding the source write fence."""
    from .postgres import _safe_collection, current_tenant

    if current_tenant() is not None:
        raise ValueError(
            "A graph binding projection requires an unscoped PostgreSQL session"
        )
    schema = _safe_collection(database.schema_name)
    await database._bootstrap_collection("node")
    await database._bootstrap_collection("edge")
    config = f"{schema}.{_CONFIG}"
    rows = f"{schema}.{_ROWS}"
    async with database._acquire_conn() as conn, conn.transaction():
        # This is operator-invoked maintenance. Readers can keep using the
        # canonical path while raw writes wait for the backfill transaction.
        await conn.execute(
            f"LOCK TABLE {schema}.edge, {schema}.node IN SHARE ROW EXCLUSIVE MODE"
        )
        if not await conn.fetchval(f"SELECT {_scope_sql(schema)}"):
            raise ValueError(
                "A graph binding projection requires unfiltered source tables"
            )
        # Keep a single-target refresh indexed even on a minimal graph schema.
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS jvspatial_binding_target_entity_v1 "
            f"ON {schema}.edge ((data #>> '{{target}}'), entity)"
        )
        await conn.execute(_ddl(schema))
        await conn.execute(
            f"INSERT INTO {config} (singleton,shape,ready) VALUES(true,$1::jsonb,false) "
            "ON CONFLICT(singleton) "
            "DO UPDATE SET shape=EXCLUDED.shape, ready=false",
            projection.configuration(),
        )
        await conn.execute(f"DELETE FROM {rows}")
        await conn.execute(
            f"""
            INSERT INTO {rows} (id, facts_valid, invalid_edge, cardinality, expected)
            WITH shape AS (SELECT shape FROM {config} WHERE singleton),
            candidates AS (
                SELECT n.id, {schema}.jvspatial_binding_facts_valid_v1(n.id,n.data,s.shape) AS valid
                FROM {schema}.node n CROSS JOIN shape s
                WHERE n.entity=s.shape->>'record_entity'
                    AND n.data #> ARRAY(SELECT jsonb_array_elements_text(s.shape->'partition_path'))
                        =s.shape->'parent_id'
            ), bindings AS (
                SELECT data #>> '{{target}}' AS target, count(*) AS cardinality,
                    bool_and(data->>'source'=s.shape->>'parent_id') AS expected,
                    bool_or(NOT {schema}.jvspatial_binding_edge_valid_v1(
                        data,s.shape->>'edge_entity')) AS invalid_edge
                FROM {schema}.edge CROSS JOIN shape s WHERE entity=s.shape->>'edge_entity'
                GROUP BY data #>> '{{target}}'
            )
            SELECT c.id,c.valid,COALESCE(b.invalid_edge,FALSE),COALESCE(b.cardinality,0),
                COALESCE(b.expected,FALSE)
            FROM candidates c LEFT JOIN bindings b ON b.target=c.id
            """
        )
        for table in ("edge", "node"):
            await conn.execute(
                f"""
                CREATE OR REPLACE TRIGGER jvspatial_binding_maintain_v1
                AFTER INSERT OR UPDATE OR DELETE ON {schema}.{table}
                FOR EACH ROW EXECUTE FUNCTION {schema}.jvspatial_binding_maintain_v1();
                CREATE OR REPLACE TRIGGER jvspatial_binding_invalidate_v1
                AFTER TRUNCATE ON {schema}.{table}
                FOR EACH STATEMENT EXECUTE FUNCTION {schema}.jvspatial_binding_invalidate_v1();
                ALTER TABLE {schema}.{table} ENABLE ALWAYS TRIGGER jvspatial_binding_maintain_v1;
                ALTER TABLE {schema}.{table} ENABLE ALWAYS TRIGGER jvspatial_binding_invalidate_v1;
                """
            )
        await conn.execute(f"ANALYZE {rows}")
        await conn.execute(
            f"UPDATE {config} SET ready=true, trigger_signature={_trigger_signature(schema)} "
            "WHERE singleton"
        )


async def available(database: Any) -> bool:
    """Check whether this schema has provisioned projection tables."""
    from .postgres import _safe_collection, current_tenant

    if current_tenant() is not None:
        return False
    schema = _safe_collection(database.schema_name)
    async with database._acquire_conn() as conn:
        return bool(
            await conn.fetchval(
                "SELECT to_regclass($1) IS NOT NULL AND to_regclass($2) IS NOT NULL",
                f"{schema}.{_CONFIG}",
                f"{schema}.{_ROWS}",
            )
        )


async def invalidate(database: Any) -> bool:
    """Stop serving and maintaining the published projection for this schema."""
    from asyncpg import UndefinedTableError

    from .postgres import _safe_collection, current_tenant

    if current_tenant() is not None:
        raise ValueError(
            "A graph binding projection requires an unscoped PostgreSQL session"
        )
    schema = _safe_collection(database.schema_name)
    try:
        async with database._acquire_conn() as conn:
            return bool(
                await conn.fetchval(
                    f"UPDATE {schema}.{_CONFIG} SET ready=false "
                    "WHERE singleton AND ready RETURNING true"
                )
            )
    except UndefinedTableError:
        return False


async def read(
    database: Any,
    projection: BindingProjection,
    *,
    max_records: int,
    max_edges: int,
    excluded_ids: Tuple[str, ...] = (),
) -> Optional[GraphBindingSummary]:
    """Read only published, exact facts with an unfiltered native scope."""
    from .postgres import _safe_collection, current_tenant

    if current_tenant() is not None:
        return None
    schema = _safe_collection(database.schema_name)
    # Gate and aggregate share a statement snapshot. Treat overflow like an
    # unsupported projection so the existing native path keeps its contract.
    from asyncpg import UndefinedTableError

    try:
        async with database._acquire_conn() as conn:
            row = await conn.fetchrow(
                f"""
                WITH ready AS (
                    SELECT 1 FROM {schema}.{_CONFIG} WHERE singleton AND ready
                        AND shape=$1::jsonb AND {_scope_sql(schema)}
                        AND trigger_signature={_trigger_signature(schema)}
                ), candidates AS (
                    SELECT facts_valid, invalid_edge, cardinality, expected
                    FROM {schema}.{_ROWS} WHERE EXISTS (SELECT 1 FROM ready)
                        AND NOT (id=ANY($3::text[])) LIMIT $2
                )
                SELECT count(*) AS matched,
                    count(*) FILTER(WHERE NOT facts_valid) AS invalid_facts,
                    count(*) FILTER(WHERE invalid_edge) AS invalid_edges,
                    count(*) FILTER(WHERE facts_valid AND NOT invalid_edge
                        AND cardinality=1 AND expected) AS bound,
                    COALESCE(sum(cardinality),0) AS edges
                FROM candidates HAVING EXISTS (SELECT 1 FROM ready)
                """,
                projection.configuration(),
                max_records + 1,
                list(excluded_ids),
            )
    except UndefinedTableError:
        return None
    if row is None or row["matched"] > max_records or row["edges"] > max_edges:
        return None
    return GraphBindingSummary(
        matched=row["matched"],
        bound=row["bound"],
        invalid_facts=row["invalid_facts"],
        invalid_edges=row["invalid_edges"],
        complete=True,
    )
