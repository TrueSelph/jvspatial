"""PostgreSQL database implementation using asyncpg + JSONB.

PostgreSQL is the recommended high-performance distributed backend for
jvspatial in production. It outperforms MongoDB on the workloads that
matter for graph + agentive applications:

* **Bulk writes** via ``COPY FROM STDIN`` — 5-20x ``bulk_write(ordered=False)``
  on typical record sizes.
* **Hot small-doc reads** (auth, session lookup) via asyncpg's binary
  + prepared-statement path — 3-5x lower latency than motor on point lookups.
* **Walker BFS** via a single recursive CTE — collapses N round trips into 1.
* **Mongo-op coverage**: JSONB + ``jsonb_path_query`` gives native pushdown
  of ``$regex``, ``$elemMatch``, ``$size``, ``$mod``, ``$type`` — all the
  operators that fall back to in-memory match on SQLite.
* **Atomicity parity**: ``UPDATE ... RETURNING`` makes ``find_one_and_update``
  / ``find_one_and_delete`` natively atomic.
* **Multi-tenant RLS**: per-connection ``app.tenant_id`` GUC + table policies
  for DB-enforced isolation.
* **pgvector**: vector columns + HNSW indexes + ``$near`` operator for
  hybrid KG-hop + vector-ANN + metadata-filter queries in one SQL.

Connection model
----------------
One :class:`asyncpg.Pool` per :class:`PostgresDB` instance, created lazily
on first use. Pool size auto-tunes via :func:`jvspatial.runtime.serverless.is_serverless_mode`:
Lambda gets ``min_size=0, max_size=3``; long-running processes get
``min_size=2, max_size=10``. Override via constructor kwargs or env.

Pooler compatibility
--------------------
When sitting behind a transaction-mode pooler (PgBouncer, RDS Proxy),
prepared statements are not safe across the pool. Pass
``pooler_mode="transaction"`` to disable asyncpg's statement cache and
use the simple-query protocol. Default ``pooler_mode="session"`` (direct
or session-pooled connection — best performance).

Neon / Aurora Serverless v2
---------------------------
* **Neon**: target the pooler endpoint (``...-pooler.region.aws.neon.tech``).
  pgvector is available on every project by default.
* **Aurora Serverless v2**: ``min_capacity=0`` gives a ~30s scale-from-zero
  cold start. Recommend ``min_capacity=0.5`` for latency-sensitive paths.
  Combine with RDS Proxy + ``pooler_mode="transaction"`` for high-concurrency
  Lambda workloads.

Schema
------
One table per collection::

    CREATE TABLE <collection> (
        id        TEXT PRIMARY KEY,
        entity    TEXT NOT NULL,
        tenant_id TEXT,           -- NULL for single-tenant deployments
        data      JSONB NOT NULL,
        _v        INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX <collection>_data_gin ON <collection> USING GIN (data);
    CREATE INDEX <collection>_entity_idx ON <collection> (entity);

RLS policies and pgvector columns are added on-demand when a tenant scope
or a vector-typed field is encountered.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import logging
import re
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from ._postgres_translate import translate_query, translate_sort
from .database import (
    BulkSaveResult,
    Database,
    decode_cursor,
    finalize_find_results,
)
from .query import QueryEngine

# Active tenant id for the current async task. ``None`` means no tenant
# scope is in effect — operations run without setting the ``app.tenant_id``
# GUC and RLS policies see no tenant. Set via :meth:`PostgresDB.tenant`.
_active_tenant: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "jvspatial_pg_active_tenant", default=None
)


def current_tenant() -> Optional[str]:
    """Return the tenant id active for the current async task, if any.

    Public read-only accessor — callers wanting to scope an operation
    set the tenant via :meth:`PostgresDB.tenant` rather than mutating the
    context var directly.
    """
    return _active_tenant.get()


logger = logging.getLogger(__name__)

try:
    import asyncpg
except ImportError:  # pragma: no cover - handled at __init__ time
    asyncpg = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - typing only
    from asyncpg.pool import Pool


# ---- safety: collection / field name validation -----------------------------

# Postgres identifier safety: alpha-num + underscore, must not start with digit,
# max 63 bytes (Postgres limit). We do NOT support quoted identifiers; pin to
# the safe ASCII subset so we never need to worry about escape edge cases.
_SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


_PARAM_RE = re.compile(r"\$(\d+)")


def _shift_placeholders(sql: str, *, shift: int) -> str:
    """Add ``shift`` to every ``$N`` placeholder in *sql*.

    Used when composing a translated query fragment into a larger
    statement that already binds parameters in slots ``$1..$shift``.
    asyncpg requires positional placeholders to be monotonically
    increasing across the whole statement.
    """
    if shift == 0:
        return sql
    return _PARAM_RE.sub(lambda m: f"${int(m.group(1)) + shift}", sql)


def _safe_collection(name: str) -> str:
    """Return ``name`` if it is a safe Postgres identifier, else raise.

    Collection names flow through to ``CREATE TABLE`` / ``SELECT FROM``
    statements; they cannot be parameterized. Reject anything outside the
    ASCII identifier subset to remove a SQL-injection vector entirely.
    """
    if not _SAFE_IDENT_RE.match(name):
        raise ValueError(
            f"PostgresDB rejects collection name {name!r}: "
            "must match [A-Za-z_][A-Za-z0-9_]{0,62}"
        )
    return name


def _pg_string_literal(value: str) -> str:
    """Quote a Python string as a PG string literal (single-quote escape)."""
    return "'" + value.replace("'", "''") + "'"


def _pg_field_extract(field_path: str) -> Optional[str]:
    """Translate a dotted field path to ``(data #>> '{a,b,c}')``.

    Returns ``None`` if any segment is unsafe. ``entity`` is a top-level
    column on the table — extract it directly rather than out of ``data``.
    """
    if field_path == "entity":
        return "entity"
    if field_path == "id":
        return "id"
    if field_path == "tenant_id":
        return "tenant_id"
    parts = field_path.split(".")
    for seg in parts:
        if not _SAFE_IDENT_RE.match(seg):
            return None
    path_literal = "{" + ",".join(parts) + "}"
    return f"(data #>> '{path_literal}')"


def _translate_partial_filter_expression(
    pfe: Dict[str, Any],
) -> Optional[str]:
    """Translate a Mongo-style ``index_partial_filter_expression`` to PG WHERE.

    Used by ``PostgresDB.create_index`` to honor the cross-backend
    partial-filter kwarg without falling through to a global unique
    index. Supports a deliberately small dialect — enough to express
    the partial filters declared by jvspatial and its downstream
    applications (entity-discriminator equality + ``$gt`` "non-empty"
    sentinels):

    - ``{field: scalar}`` → ``<extract> = '<literal>'``
    - ``{field: {"$eq": scalar}}`` → same
    - ``{field: {"$gt": scalar}}`` → ``<extract> > '<literal>'``
    - ``{field: {"$exists": True}}`` → ``<extract> IS NOT NULL``
    - ``{field: {"$exists": False}}`` → ``<extract> IS NULL``

    Top-level keys are AND-ed together. Returns ``None`` for any shape
    outside this dialect — callers raise so a partial unique index is
    never silently demoted to a global unique.
    """
    if not isinstance(pfe, dict) or not pfe:
        return None
    clauses: List[str] = []
    for field, spec in pfe.items():
        extract = _pg_field_extract(field)
        if extract is None:
            return None
        if isinstance(spec, dict):
            if len(spec) != 1:
                return None
            op, val = next(iter(spec.items()))
            if op == "$eq":
                if not isinstance(val, (str, int, float, bool)):
                    return None
                if isinstance(val, bool):
                    clauses.append(f"{extract} = '{str(val).lower()}'")
                elif isinstance(val, (int, float)):
                    clauses.append(f"({extract})::numeric = {val}")
                else:
                    clauses.append(f"{extract} = {_pg_string_literal(val)}")
            elif op == "$gt":
                if not isinstance(val, (str, int, float)):
                    return None
                if isinstance(val, (int, float)):
                    clauses.append(f"({extract})::numeric > {val}")
                else:
                    clauses.append(f"{extract} > {_pg_string_literal(val)}")
            elif op == "$exists":
                if val:
                    clauses.append(f"{extract} IS NOT NULL")
                else:
                    clauses.append(f"{extract} IS NULL")
            else:
                return None
        elif isinstance(spec, bool):
            clauses.append(f"{extract} = '{str(spec).lower()}'")
        elif isinstance(spec, (int, float)):
            clauses.append(f"({extract})::numeric = {spec}")
        elif isinstance(spec, str):
            clauses.append(f"{extract} = {_pg_string_literal(spec)}")
        else:
            return None
    return " AND ".join(clauses)


# ---- adapter ----------------------------------------------------------------


class PostgresDB(Database):
    """PostgreSQL database adapter backed by asyncpg + JSONB.

    The adapter is the recommended production backend for jvspatial. See
    the module docstring for the why; see :func:`create_database` for the
    full set of configuration knobs.
    """

    # Postgres supports ACID transactions natively. The base
    # ``begin_transaction`` machinery is wired in a later patch
    # (C4: PG atomicity) — for now ``supports_transactions`` advertises
    # the capability so callers can branch on it. Until ``begin_transaction``
    # lands, transactional context is offered only via ``UPDATE … RETURNING``
    # at the operation level (atomic single-row update).
    supports_transactions: bool = True

    def __init__(
        self,
        dsn: Optional[str] = None,
        *,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        pooler_mode: str = "session",
        command_timeout: float = 60.0,
        schema_name: str = "public",
    ) -> None:
        """Initialize the Postgres adapter.

        Args:
            dsn: ``postgresql://<user>:<password>@<host>:<port>/<dbname>`` connection string.
                Reads ``JVSPATIAL_POSTGRES_DSN`` env when omitted.
            min_size: Minimum connections held in the pool. Auto-tuned by
                serverless mode when omitted (Lambda: 0, long-running: 2).
                Also read from ``JVSPATIAL_POSTGRES_MIN_POOL_SIZE``.
            max_size: Maximum connections in the pool. Auto-tuned by
                serverless mode when omitted (Lambda: 3, long-running: 10).
                Also read from ``JVSPATIAL_POSTGRES_MAX_POOL_SIZE``.
            pooler_mode: ``"session"`` (default; best performance, requires
                direct or session-pooled connection) or ``"transaction"``
                (compatible with PgBouncer / RDS Proxy in transaction-pool
                mode — disables statement cache, uses simple-query protocol).
            command_timeout: Per-statement timeout in seconds.
            schema_name: Postgres schema to host the collection tables in.
                Defaults to ``public``. Must be an existing schema.

        Raises:
            ImportError: ``asyncpg`` is not installed.
            ValueError: ``pooler_mode`` is not ``"session"`` or ``"transaction"``.
        """
        if asyncpg is None:  # pragma: no cover
            raise ImportError(
                "asyncpg is required for the Postgres backend. "
                "Install it with: pip install jvspatial[postgres]"
            )
        if pooler_mode not in ("session", "transaction"):
            raise ValueError(
                f"pooler_mode must be 'session' or 'transaction', got {pooler_mode!r}"
            )

        from jvspatial.env import env
        from jvspatial.runtime.serverless import is_serverless_mode

        self.dsn = dsn or env(
            "JVSPATIAL_POSTGRES_DSN",
            default="postgresql://postgres:postgres@localhost:5432/jvdb",  # pragma: allowlist secret
        )

        # Auto-tune pool size by deployment mode.
        serverless = is_serverless_mode()
        env_min = env("JVSPATIAL_POSTGRES_MIN_POOL_SIZE", parse=int)
        env_max = env("JVSPATIAL_POSTGRES_MAX_POOL_SIZE", parse=int)
        default_min = 0 if serverless else 2
        default_max = 3 if serverless else 10
        self.min_size = min_size if min_size is not None else (env_min or default_min)
        self.max_size = max_size if max_size is not None else (env_max or default_max)

        self.pooler_mode = pooler_mode
        self.command_timeout = command_timeout
        self.schema_name = schema_name

        self._pool: Optional["Pool"] = None
        self._pool_lock = asyncio.Lock()

        # Collections we've already created the table + base indexes for.
        # Avoids running CREATE TABLE IF NOT EXISTS on the hot path.
        self._collections_bootstrapped: Set[str] = set()

        # Vector columns configured per collection. Map collection ->
        # {field_name: dim}. Populated by :meth:`enable_vector_column`;
        # read by save / bulk_save / translator to route embeddings to
        # the dedicated column.
        self._vector_columns: Dict[str, Dict[str, int]] = {}

    # ---- pool lifecycle ----------------------------------------------------

    async def _ensure_pool(self) -> "Pool":
        """Lazily create the asyncpg pool. Idempotent + concurrency-safe."""
        if self._pool is not None:
            return self._pool
        async with self._pool_lock:
            if self._pool is not None:  # re-check under lock
                return self._pool

            create_kwargs: Dict[str, Any] = {
                "dsn": self.dsn,
                "min_size": self.min_size,
                "max_size": self.max_size,
                "command_timeout": self.command_timeout,
            }
            if self.pooler_mode == "transaction":
                # Required for PgBouncer / RDS Proxy transaction-pool mode:
                # disable asyncpg's prepared-statement cache and bind
                # parameters via the simple-query protocol.
                create_kwargs["statement_cache_size"] = 0

            logger.debug(
                "PostgresDB: creating pool (min=%d max=%d mode=%s)",
                self.min_size,
                self.max_size,
                self.pooler_mode,
            )
            self._pool = await asyncpg.create_pool(**create_kwargs)
            return self._pool

    async def close(self) -> None:
        """Close the connection pool. Safe to call multiple times."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._collections_bootstrapped.clear()

    # ---- tenant scope (C6) -------------------------------------------------

    @contextlib.asynccontextmanager
    async def tenant(self, tenant_id: str) -> AsyncIterator[None]:
        """Scope all PG ops in this block to a specific tenant.

        Inside the block, every connection checked out from the pool
        opens an explicit transaction and runs ``SET LOCAL app.tenant_id``
        before any user query. RLS policies installed via
        :meth:`enable_rls` then filter rows where ``tenant_id`` does not
        match the GUC — DB-enforced isolation that survives malicious
        query crafting.

        The context manager is async-task safe via :class:`contextvars`:
        nested tenant scopes shadow correctly, sibling tasks have
        independent scopes.

        Usage::

            async with db.tenant("acme-42"):
                user = await db.get("user", "u1")  # only returns acme-42 rows

        Args:
            tenant_id: Opaque string identifying the tenant. Must be
                non-empty (empty / None disables tenant scope — use
                ``enable_rls(... required=False)`` for that explicitly).
        """
        if not tenant_id:
            raise ValueError("PostgresDB.tenant: tenant_id must be non-empty")
        token = _active_tenant.set(str(tenant_id))
        try:
            yield
        finally:
            _active_tenant.reset(token)

    @contextlib.asynccontextmanager
    async def _acquire_conn(self) -> AsyncIterator[Any]:
        """Acquire a pool connection, applying tenant scope if active.

        When :meth:`tenant` is in effect for the current async task, the
        connection is opened with a fresh transaction and ``SET LOCAL
        app.tenant_id`` is issued before the caller sees it. Without a
        tenant scope, a plain pool checkout is returned (no transaction
        overhead).

        Use this in every PG operation that touches user data so the
        tenant filter applies uniformly. Operations that explicitly
        manage their own transaction (e.g. :meth:`find_one_and_update`)
        set the GUC themselves inside their transaction.
        """
        pool = await self._ensure_pool()
        tenant_id = _active_tenant.get()
        async with pool.acquire() as conn:
            if tenant_id is None:
                yield conn
                return
            # SET LOCAL requires a transaction; wrap the user's work in
            # one and commit on success.
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)",
                    tenant_id,
                )
                yield conn

    # ---- RLS install (C6) --------------------------------------------------

    async def enable_rls(
        self,
        collection: str,
        *,
        tenant_required: bool = True,
    ) -> None:
        """Enable row-level security on ``collection`` keyed by ``tenant_id``.

        Installs a policy that admits a row iff its ``tenant_id`` matches
        the current value of the ``app.tenant_id`` GUC. The GUC is set
        per-request by :meth:`tenant`; with no tenant scope in effect
        and ``tenant_required=True`` (the default), no rows are visible
        — a safer default than allowing accidental cross-tenant reads.

        Args:
            collection: Table to protect.
            tenant_required: When ``True`` (default), the policy rejects
                rows whose ``tenant_id`` does not match the GUC; calls
                made without ``tenant(...)`` see nothing. When ``False``,
                the policy admits rows with ``tenant_id IS NULL`` as a
                "global" partition — useful for migration from a
                single-tenant deployment.

        Idempotent: re-enabling RLS on a table that already has the
        policy is a no-op. The policy can be removed (along with RLS)
        via ``ALTER TABLE ... DISABLE ROW LEVEL SECURITY`` from a DB
        admin session.

        Note: the policy uses ``current_setting('app.tenant_id', true)``
        — the second argument suppresses the error when the GUC is
        unset, returning empty string. The policy then compares to NULL
        / empty as appropriate.
        """
        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)
        pool = await self._ensure_pool()

        if tenant_required:
            policy_expr = (
                "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')"
            )
        else:
            policy_expr = (
                "tenant_id IS NULL OR "
                "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')"
            )

        policy_name = f"{col}_tenant_isolation"
        # ALTER + CREATE POLICY both error if duplicated; check + drop +
        # recreate so re-runs are idempotent. ``DROP POLICY IF EXISTS``
        # is supported on PG 9.5+.
        async with pool.acquire() as conn:
            await conn.execute(f"ALTER TABLE {schema}.{col} ENABLE ROW LEVEL SECURITY")
            # FORCE applies the policy to the table owner too. Without
            # this, the owner role bypasses RLS and gets cross-tenant
            # access — the exact footgun multi-tenant SaaS must avoid.
            # Production users running with a dedicated app role (not
            # owner) can drop the FORCE; the safer default protects the
            # common case where the app connects as the owning role.
            await conn.execute(f"ALTER TABLE {schema}.{col} FORCE ROW LEVEL SECURITY")
            await conn.execute(f"DROP POLICY IF EXISTS {policy_name} ON {schema}.{col}")
            await conn.execute(
                f"CREATE POLICY {policy_name} ON {schema}.{col} "
                f"USING ({policy_expr}) WITH CHECK ({policy_expr})"
            )

    # ---- schema bootstrap --------------------------------------------------

    async def _bootstrap_collection(self, collection: str) -> None:
        """Create the table + base indexes for ``collection`` if missing.

        Idempotent + cached. Safe to call from any code path before a CRUD
        op; the cost on the warm path after first call is one set membership
        check.
        """
        if collection in self._collections_bootstrapped:
            return
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # Single round trip — CREATE IF NOT EXISTS is cheap when the
            # table already exists.
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {schema}.{col} (
                    id         TEXT PRIMARY KEY,
                    entity     TEXT NOT NULL,
                    tenant_id  TEXT,
                    data       JSONB NOT NULL,
                    _v         INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS {col}_data_gin
                    ON {schema}.{col} USING GIN (data jsonb_path_ops);
                CREATE INDEX IF NOT EXISTS {col}_entity_idx
                    ON {schema}.{col} (entity);
                CREATE INDEX IF NOT EXISTS {col}_tenant_idx
                    ON {schema}.{col} (tenant_id)
                    WHERE tenant_id IS NOT NULL;
                """
            )
        self._collections_bootstrapped.add(collection)

    # ---- payload helpers ---------------------------------------------------

    @staticmethod
    def _split_payload(data: Dict[str, Any]) -> Tuple[str, str, Optional[str], str]:
        """Extract (id, entity, tenant_id, data_json) from a record dict.

        ``tenant_id`` is optional and reads from ``data["tenant_id"]`` when
        present — multi-tenant callers set it via ``Object``-level field
        declaration; single-tenant callers leave it NULL.

        Raises:
            ValueError: ``data`` lacks an ``id`` field.
        """
        if "id" not in data:
            raise ValueError("PostgresDB.save requires data with an 'id' field")
        rec_id = str(data["id"])
        entity = str(data.get("entity") or "")
        tenant_id = data.get("tenant_id")
        tenant = str(tenant_id) if tenant_id is not None else None
        # asyncpg accepts a Python str for jsonb columns (it round-trips
        # via the JSONB codec); using json.dumps here keeps the serialization
        # cost explicit and lets callers see the exact bytes on the wire.
        data_json = json.dumps(data)
        return rec_id, entity, tenant, data_json

    @staticmethod
    def _encode_vector(value: Any) -> str:
        """Encode a Python list / tuple as a pgvector literal string.

        pgvector accepts ``'[1.0, 2.0, 3.0]'``-style text input; we use
        the string form so we don't take a hard dependency on the
        ``pgvector`` Python codec (callers who install ``jvspatial[pgvector]``
        get the codec automatically; everyone else can still set vectors
        via the text path).

        Raises:
            TypeError: ``value`` is not a list/tuple of numbers.
        """
        if not isinstance(value, (list, tuple)):
            raise TypeError(
                f"vector value must be a list/tuple of numbers, got {type(value).__name__}"
            )
        try:
            floats = [float(v) for v in value]
        except (TypeError, ValueError) as exc:
            raise TypeError(f"vector value contains non-numeric entry: {exc}") from exc
        # JSON-array style matches pgvector's input parser.
        return "[" + ",".join(repr(f) for f in floats) + "]"

    @staticmethod
    def _record_from_row(row: Any) -> Dict[str, Any]:
        """Restore the original record dict from a Postgres row.

        We store the full record in the ``data`` JSONB column. The other
        columns (``id``, ``entity``, ``tenant_id``, ``_v``) are denormalized
        copies for indexing — readers always see the JSONB blob.
        """
        if row is None:
            return None  # type: ignore[return-value]
        data = row["data"]
        # asyncpg returns jsonb as already-decoded Python types when the
        # default codec is in use; if a caller plugged in a non-decoding
        # codec, fall back to json.loads.
        if isinstance(data, (bytes, bytearray, memoryview)):
            data = json.loads(bytes(data).decode("utf-8"))
        elif isinstance(data, str):
            data = json.loads(data)
        return data  # type: ignore[no-any-return]

    # ---- CRUD --------------------------------------------------------------

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert a record. Returns the saved record dict.

        Uses ``INSERT ... ON CONFLICT (id) DO UPDATE`` so save is idempotent
        and atomic per-row.
        """
        await self._bootstrap_collection(collection)
        rec_id, entity, tenant, data_json = self._split_payload(data)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)

        # Extract any vector-typed fields configured for this collection.
        vector_cols = self._vector_columns.get(collection, {})
        vec_updates: Dict[str, str] = {}
        for fname in vector_cols:
            if fname in data and data[fname] is not None:
                vec_updates[fname] = self._encode_vector(data[fname])

        async with self._acquire_conn() as conn:
            await conn.execute(
                f"""
                INSERT INTO {schema}.{col} (id, entity, tenant_id, data, updated_at)
                VALUES ($1, $2, $3, $4::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    entity     = EXCLUDED.entity,
                    tenant_id  = EXCLUDED.tenant_id,
                    data       = EXCLUDED.data,
                    updated_at = NOW()
                """,
                rec_id,
                entity,
                tenant,
                data_json,
            )
            # Second round trip when vector columns are configured. Keeps
            # the hot non-vector path single-statement; pays one extra
            # query only when embeddings are part of the record.
            if vec_updates:
                set_clauses: List[str] = []
                bind: List[Any] = []
                for i, (fname, vec) in enumerate(vec_updates.items(), start=1):
                    set_clauses.append(f"{fname} = ${i}::vector")
                    bind.append(vec)
                bind.append(rec_id)
                await conn.execute(
                    f"UPDATE {schema}.{col} SET {', '.join(set_clauses)} "
                    f"WHERE id = ${len(bind)}",
                    *bind,
                )
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single record by id."""
        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)
        async with self._acquire_conn() as conn:
            row = await conn.fetchrow(
                f"SELECT data FROM {schema}.{col} WHERE id = $1", str(id)
            )
        return self._record_from_row(row) if row is not None else None

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by id. Silent if not present."""
        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)
        async with self._acquire_conn() as conn:
            await conn.execute(f"DELETE FROM {schema}.{col} WHERE id = $1", str(id))

    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Find records matching ``query``.

        Pushes the full Mongo-style query down to JSONB SQL via
        :func:`translate_query`. When the translator cannot express some
        portion (``$where`` / ``$text`` / unknown operator), falls back to
        loading the collection and applying :class:`QueryEngine.match`
        in-Python — same safety net SQLite uses.
        """
        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)

        # Peel off any $near operator so we can translate the rest of the
        # query normally and then append ORDER BY <field> <=> <vec>.
        filtered_query, vec_field, vec_literal, vec_limit, vec_ops = (
            self._pop_vector_clause(collection, query)
            if query
            else (query, None, None, None, None)
        )

        translated = translate_query(filtered_query) if filtered_query else ("", [])
        if translated is None:
            # Translator refused; fall back to in-Python filtering.
            async with self._acquire_conn() as conn:
                rows = await conn.fetch(f"SELECT data FROM {schema}.{col}")
            records = [self._record_from_row(r) for r in rows]
            records = [r for r in records if QueryEngine.match(r, query)]
            return finalize_find_results(records, sort=sort, limit=limit)

        where_sql, params = translated
        sort_sql = translate_sort(sort) if vec_field is None else None

        clauses: List[str] = []
        if where_sql:
            clauses.append(where_sql)
        where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        # Vector ORDER BY wins over the user-supplied sort when both are
        # present — the only sensible composition for hybrid retrieval.
        if vec_field is not None:
            params = list(params) + [vec_literal]
            order_clause = f" ORDER BY {vec_field} {vec_ops} ${len(params)}::vector"
        elif sort_sql:
            order_clause = f" ORDER BY {sort_sql}"
        else:
            order_clause = ""

        effective_limit = limit
        if vec_limit is not None and (limit is None or vec_limit < limit):
            effective_limit = vec_limit
        limit_clause = ""
        if effective_limit is not None:
            params = list(params) + [int(effective_limit)]
            limit_clause = f" LIMIT ${len(params)}"

        sql = (
            f"SELECT data FROM {schema}.{col}{where_clause}{order_clause}{limit_clause}"
        )
        async with self._acquire_conn() as conn:
            rows = await conn.fetch(sql, *params)
        records = [self._record_from_row(r) for r in rows]

        # Sort pushdown may have failed (translate_sort returned None);
        # honor it in-memory in that case so the contract still holds.
        if sort and sort_sql is None:
            records = finalize_find_results(records, sort=sort, limit=None)
        return records

    async def count(
        self, collection: str, query: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count records matching ``query``.

        Empty query → SQL ``COUNT(*)`` (single round trip).
        Translatable query → ``SELECT COUNT(*) ... WHERE <translated>``.
        Untranslatable → falls back to :meth:`find` + ``len``.
        """
        q = query or {}
        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)

        if not q:
            async with self._acquire_conn() as conn:
                row = await conn.fetchrow(f"SELECT COUNT(*) AS n FROM {schema}.{col}")
            return int(row["n"]) if row else 0

        translated = translate_query(q)
        if translated is None:
            results = await self.find(collection, q)
            return len(results)
        where_sql, params = translated
        clause = f" WHERE {where_sql}" if where_sql else ""
        async with self._acquire_conn() as conn:
            row = await conn.fetchrow(
                f"SELECT COUNT(*) AS n FROM {schema}.{col}{clause}", *params
            )
        return int(row["n"]) if row else 0

    async def find_many(
        self, collection: str, ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Bulk-fetch by id with a single ``WHERE id = ANY($1)`` round trip."""
        if not ids:
            return {}
        unique_ids = list(dict.fromkeys(str(i) for i in ids))
        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)
        async with self._acquire_conn() as conn:
            rows = await conn.fetch(
                f"SELECT id, data FROM {schema}.{col} WHERE id = ANY($1::text[])",
                unique_ids,
            )
        out: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            out[row["id"]] = self._record_from_row(row)
        return out

    async def bulk_save_detailed(
        self, collection: str, records: List[Dict[str, Any]]
    ) -> BulkSaveResult:
        """Bulk upsert via ``COPY FROM STDIN`` into a temp table + merge.

        This is the fastest write path Postgres exposes:

        1. Create a session-temp table with the same shape as the target
           (skipped if it already exists for this transaction).
        2. ``COPY`` all rows into it (binary protocol, ~10x of ``executemany``).
        3. ``INSERT INTO target ... SELECT FROM temp ... ON CONFLICT DO UPDATE``
           — single transactional merge.

        On error during the COPY, all rows fail together (the merge step
        never runs). For partial-success semantics in that case we fall back
        to per-record saves so callers can still inspect ``failed_ids``.
        """
        if not records:
            return BulkSaveResult(attempted=0, saved=0, failed_ids=[])
        for idx, r in enumerate(records):
            if "id" not in r:
                raise ValueError(f"bulk_save: record at index {idx} has no 'id' field")

        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)

        # Build the row tuples once.
        rows: List[Tuple[str, str, Optional[str], str]] = [
            self._split_payload(r) for r in records
        ]

        pool = await self._ensure_pool()
        attempted = len(records)
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        f"""
                        CREATE TEMP TABLE IF NOT EXISTS _jvs_bulk_{col} (
                            id        TEXT,
                            entity    TEXT,
                            tenant_id TEXT,
                            data      JSONB
                        ) ON COMMIT DROP
                        """
                    )
                    await conn.copy_records_to_table(
                        f"_jvs_bulk_{col}",
                        records=rows,
                        columns=("id", "entity", "tenant_id", "data"),
                    )
                    await conn.execute(
                        f"""
                        INSERT INTO {schema}.{col} (id, entity, tenant_id, data, updated_at)
                        SELECT id, entity, tenant_id, data, NOW() FROM _jvs_bulk_{col}
                        ON CONFLICT (id) DO UPDATE SET
                            entity     = EXCLUDED.entity,
                            tenant_id  = EXCLUDED.tenant_id,
                            data       = EXCLUDED.data,
                            updated_at = NOW()
                        """
                    )
            return BulkSaveResult(attempted=attempted, saved=attempted, failed_ids=[])
        except Exception as exc:
            # The fast path failed — fall back to per-record saves so callers
            # can still see which IDs survived.
            logger.warning(
                "PostgresDB.bulk_save fast path failed (%s); falling back to per-record",
                exc,
            )
            saved = 0
            failed_ids: List[str] = []
            for r in records:
                try:
                    await self.save(collection, dict(r))
                    saved += 1
                except Exception as inner:
                    logger.warning(
                        "PostgresDB.bulk_save: record id=%r failed: %s",
                        r.get("id"),
                        inner,
                    )
                    failed_ids.append(str(r.get("id", "")))
            return BulkSaveResult(
                attempted=attempted, saved=saved, failed_ids=failed_ids
            )

    # ---- index management --------------------------------------------------

    async def create_index(
        self,
        collection: str,
        field_or_fields: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        **kwargs: Any,
    ) -> None:
        """Create a functional B-tree index on a JSONB field path.

        Field paths use dot notation (``"context.user.id"``) and translate
        to ``json_extract`` style ``(data #>> '{context,user,id}')``. Compound
        index inputs (``[(field, dir)]``) are honored; ``unique=True`` adds
        ``CREATE UNIQUE INDEX``. Postgres-specific kwargs (``where``,
        ``method``) are accepted via ``**kwargs``.
        """
        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)

        # Normalize input shape.
        if isinstance(field_or_fields, str):
            fields: List[Tuple[str, int]] = [(field_or_fields, 1)]
        else:
            fields = list(field_or_fields)

        # Build the column expression list.
        col_exprs: List[str] = []
        name_parts: List[str] = []
        for field_path, direction in fields:
            for seg in field_path.split("."):
                if not _SAFE_IDENT_RE.match(seg):
                    raise ValueError(
                        f"PostgresDB.create_index rejects field path {field_path!r}: "
                        f"segment {seg!r} must be a safe identifier"
                    )
            path_literal = "{" + ",".join(field_path.split(".")) + "}"
            direction_sql = "ASC" if direction == 1 else "DESC"
            col_exprs.append(f"(data #>> '{path_literal}') {direction_sql}")
            name_parts.append(field_path.replace(".", "_"))

        unique_sql = "UNIQUE " if unique else ""
        index_name = f"{col}_{'_'.join(name_parts)}_idx"
        if unique:
            index_name = f"{col}_{'_'.join(name_parts)}_uniq"

        where_clause = ""
        partial = kwargs.get("where")
        if partial:
            # We don't try to parse the partial expression — caller is
            # responsible for getting it right. We do require it to be a
            # simple Postgres predicate string.
            where_clause = f" WHERE {partial}"
        else:
            # Translate Mongo-style ``index_partial_filter_expression``
            # (the cross-backend kwarg used by ``attribute(index_unique=...,
            # index_partial_filter_expression=...)``) into a PG WHERE
            # clause. The Mongo form scopes a unique index to a subset of
            # rows (e.g. only Agent-discriminator nodes). Without this
            # translation the index becomes globally unique across the
            # whole collection, which collides the moment any other Node
            # class writes the same field value (real-world breakage
            # surfaced when embedded jvagent's ``Agent.name`` unique
            # constraint applied to every Node in the host's ``node``
            # collection).
            # ``get_indexes()`` emits the partial filter under several
            # name variants depending on the declaration site
            # (``attribute(...)``, ``@compound_index(...)``, the raw
            # MongoDB key). Accept all three so the translator fires
            # regardless of which annotation generated the index_def.
            pfe = (
                kwargs.get("index_partial_filter_expression")
                or kwargs.get("partial_filter_expression")
                or kwargs.get("partialFilterExpression")
            )
            if pfe:
                translated = _translate_partial_filter_expression(pfe)
                if translated is None:
                    raise ValueError(
                        "PostgresDB.create_index: cannot translate "
                        f"index_partial_filter_expression {pfe!r} to a "
                        "PG WHERE clause. Pass an explicit ``where=`` "
                        "argument or use a supported filter shape "
                        "(equality / $gt / $exists on safe field paths "
                        "with scalar values)."
                    )
                where_clause = f" WHERE {translated}"

        method = kwargs.get("method", "btree")
        if method not in ("btree", "hash", "gin", "gist", "brin"):
            raise ValueError(f"Unsupported index method: {method!r}")

        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"CREATE {unique_sql}INDEX IF NOT EXISTS {index_name} "
                f"ON {schema}.{col} USING {method} ({', '.join(col_exprs)})"
                f"{where_clause}"
            )

    # ---- atomic compound ops (C4) ------------------------------------------

    async def find_one_and_delete(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Atomically find + delete the first matching record.

        Uses ``DELETE ... RETURNING data`` so the lookup and remove happen
        in a single round trip with no read-modify-write race.

        For queries that cannot be expressed in pushdown SQL (``$where`` /
        ``$text``), falls back to the base-class read-modify-write path
        — same safety net the SQLite adapter relies on.
        """
        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)

        from .database import _normalize_id_query

        q = _normalize_id_query(query)
        translated = translate_query(q) if q else ("", [])
        if translated is None:
            return await super().find_one_and_delete(collection, query)

        where_sql, params = translated
        clause = f" WHERE {where_sql}" if where_sql else ""
        # ctid-based scope lets us delete exactly one row even when the
        # predicate would match more — matches MongoDB find_one_and_delete
        # semantics.
        sql = (
            f"DELETE FROM {schema}.{col} "
            f"WHERE ctid = (SELECT ctid FROM {schema}.{col}{clause} LIMIT 1) "
            f"RETURNING data"
        )
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)
        return self._record_from_row(row) if row is not None else None

    async def find_one_and_update(
        self,
        collection: str,
        query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Atomically find + update the first matching record.

        We model the operation as ``SELECT ... FOR UPDATE`` over a single
        row scoped by ``ctid``, then apply the Mongo-style update in
        Python and write back with ``save()``. The ``FOR UPDATE`` lock is
        held until the surrounding transaction commits, so concurrent
        writers serialize on the same row — same safety guarantee as the
        MongoDB-native ``findOneAndUpdate``.

        For queries the translator can't express, falls back to the
        base-class implementation.
        """
        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)

        from .database import _normalize_id_query

        q = _normalize_id_query(query)
        translated = translate_query(q) if q else ("", [])
        if translated is None:
            return await super().find_one_and_update(
                collection, query, update, upsert=upsert
            )

        where_sql, params = translated
        clause = f" WHERE {where_sql}" if where_sql else ""
        pool = await self._ensure_pool()

        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"SELECT ctid, data FROM {schema}.{col}{clause} "
                    f"LIMIT 1 FOR UPDATE",
                    *params,
                )
                if row is None:
                    if not upsert:
                        return None
                    doc: Dict[str, Any] = {}
                    doc_id = query.get("_id", query.get("id"))
                    if doc_id is not None:
                        doc["_id"] = doc_id
                        doc["id"] = str(doc_id)
                    QueryEngine.apply_update(doc, update, apply_set_on_insert=True)
                else:
                    doc = self._record_from_row(row)
                    QueryEngine.apply_update(doc, update, apply_set_on_insert=False)

                record_id = doc.get("id", doc.get("_id"))
                if record_id is not None:
                    doc["id"] = str(record_id)

                # Inline save (we own the transaction).
                rec_id, entity, tenant, data_json = self._split_payload(doc)
                await conn.execute(
                    f"""
                    INSERT INTO {schema}.{col} (id, entity, tenant_id, data, updated_at)
                    VALUES ($1, $2, $3, $4::jsonb, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        entity     = EXCLUDED.entity,
                        tenant_id  = EXCLUDED.tenant_id,
                        data       = EXCLUDED.data,
                        updated_at = NOW()
                    """,
                    rec_id,
                    entity,
                    tenant,
                    data_json,
                )
                return doc

    def _pop_vector_clause(
        self, collection: str, query: Dict[str, Any]
    ) -> Tuple[
        Dict[str, Any], Optional[str], Optional[str], Optional[int], Optional[str]
    ]:
        """Peel a ``$near`` clause out of ``query`` if one targets a vector column.

        Returns ``(filtered_query, field_name, vector_literal, limit, ops)``.
        When the query has no ``$near`` on a configured vector column the
        first tuple is the unchanged query and the rest are ``None``.

        The ``ops`` string is the distance operator (`<=>` cosine,
        `<->` L2, `<#>` inner product) — picked from the column's index
        configuration. v1 defaults to `<=>` (cosine).
        """
        vector_cols = self._vector_columns.get(collection)
        if not vector_cols or not query:
            return query, None, None, None, None
        filtered = dict(query)
        for fname in vector_cols:
            if fname not in filtered:
                continue
            cond = filtered[fname]
            if not isinstance(cond, dict) or "$near" in cond is False:
                continue
            if "$near" not in cond:
                continue
            vec_value = cond["$near"]
            try:
                vec_literal = self._encode_vector(vec_value)
            except TypeError:
                # Bad vector — leave the clause alone so the
                # default translator can fail loudly.
                continue
            limit_val = cond.get("$limit")
            limit = int(limit_val) if isinstance(limit_val, int) else None
            # Strip the vector ops from the field condition so the
            # general translator doesn't try to push it down. If there
            # are other operators on the same field they remain.
            rest = {k: v for k, v in cond.items() if k not in ("$near", "$limit")}
            if rest:
                filtered[fname] = rest
            else:
                filtered.pop(fname, None)
            # v1 always cosine — index ops choice baked in at
            # enable_vector_column() time.
            return filtered, fname, vec_literal, limit, "<=>"
        return query, None, None, None, None

    # ---- pgvector integration (C7) -----------------------------------------

    async def enable_vector_column(
        self,
        collection: str,
        field_name: str,
        *,
        dim: int,
        index: str = "hnsw",
        ops: str = "vector_cosine_ops",
        m: int = 16,
        ef_construction: int = 64,
    ) -> None:
        """Add a pgvector column + ANN index to ``collection``.

        The column is added to the table (separate from the JSONB ``data``
        blob) so vector ops use proper numeric storage and a native ANN
        index. Vector values flow in via ``save`` / ``bulk_save`` —
        callers put the embedding in ``data[field_name]`` and the adapter
        copies it to the dedicated column.

        Idempotent: re-enabling a vector column with the same dim is a
        no-op. Changing ``dim`` requires manually dropping and recreating
        the column (we refuse to silently destroy data).

        Args:
            collection: Target table.
            field_name: Vector attribute name (also the column name). Must
                be a safe identifier.
            dim: Vector dimension. Common: 384 (MiniLM), 768 (MPNet/BGE),
                1024 (BGE-large), 1536 (OpenAI ada-002), 3072 (OpenAI
                text-embedding-3-large).
            index: ``"hnsw"`` (default, best recall/latency) or
                ``"ivfflat"`` (lower memory, slightly worse recall).
            ops: Distance operator class. ``vector_cosine_ops`` (default;
                pair with ``<=>``), ``vector_l2_ops`` (pair with ``<->``),
                or ``vector_ip_ops`` (pair with ``<#>`` for inner product).
            m: HNSW parameter — max connections per node. Higher = better
                recall, more memory. Default 16 is the pgvector default.
            ef_construction: HNSW build-time accuracy. Higher = slower
                build, better recall. Default 64 is the pgvector default.

        Raises:
            ImportError: pgvector codec isn't installed.
            ValueError: Unsafe identifier, bad ``dim``, or unsupported
                index / ops choice.
        """
        if dim <= 0 or dim > 16000:
            raise ValueError(f"vector dim out of range: {dim}")
        if not _SAFE_IDENT_RE.match(field_name):
            raise ValueError(f"unsafe vector field name: {field_name!r}")
        if index not in ("hnsw", "ivfflat"):
            raise ValueError(f"unsupported vector index method: {index!r}")
        if ops not in ("vector_cosine_ops", "vector_l2_ops", "vector_ip_ops"):
            raise ValueError(f"unsupported vector ops: {ops!r}")

        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)
        index_name = f"{col}_{field_name}_{index}_idx"

        async with self._pool_lock:
            pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            # Install extension if not present (no-op when already installed).
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            # Add the column. ``ADD COLUMN IF NOT EXISTS`` is PG 9.6+; we
            # rely on it. asyncpg surfaces a DuplicateColumnError if the
            # column exists with a different type — let it propagate so
            # callers see the real conflict.
            await conn.execute(
                f"ALTER TABLE {schema}.{col} "
                f"ADD COLUMN IF NOT EXISTS {field_name} vector({dim})"
            )
            # Index params for HNSW are passed via WITH (...). IVFFlat
            # needs a lists= parameter; skip it for v1 (HNSW is the
            # recommended default).
            if index == "hnsw":
                params_clause = f" WITH (m = {m}, ef_construction = {ef_construction})"
            else:
                params_clause = ""
            await conn.execute(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON {schema}.{col} "
                f"USING {index} ({field_name} {ops}){params_clause}"
            )
        # Remember the column for save-path extraction. Mapping is
        # collection -> { field_name: dim }.
        self._vector_columns.setdefault(collection, {})[field_name] = dim

    # ---- cursor pagination (F1) --------------------------------------------

    async def find_iter(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        sort: Optional[List[Tuple[str, int]]] = None,
        batch_size: int = 100,
        cursor: Optional[bytes] = None,
    ) -> "AsyncIterator[Dict[str, Any]]":
        """Native keyset pagination via JSONB predicate composition.

        Holds one pool connection for the duration of the iteration so
        consecutive page fetches share state cleanly. The keyset clause
        is composed into the WHERE alongside the user query so the
        GIN / functional indexes on the JSONB blob still apply.

        Args / yields: see :meth:`Database.find_iter` on the base class.
        """
        await self._bootstrap_collection(collection)
        col = _safe_collection(collection)
        schema = _safe_collection(self.schema_name)

        effective_sort: List[Tuple[str, int]] = list(sort) if sort else [("id", 1)]
        sort_sql = translate_sort(effective_sort)
        if sort_sql is None:
            # Sort can't push down — fall back to base default impl.
            async for rec in super().find_iter(
                collection,
                query,
                sort=effective_sort,
                batch_size=batch_size,
                cursor=cursor,
            ):
                yield rec
            return

        last_id: Optional[str] = None
        if cursor is not None:
            decoded = decode_cursor(cursor)
            if decoded is not None:
                last_id = decoded.get("id")

        translated = translate_query(query) if query else ("", [])
        if translated is None:
            async for rec in super().find_iter(
                collection,
                query,
                sort=effective_sort,
                batch_size=batch_size,
                cursor=cursor,
            ):
                yield rec
            return
        base_where, base_params = translated

        # Hold ONE connection for the entire iteration. Avoids the
        # pool-acquire / release cycle per page and the stale-state
        # races that come with it under pytest-asyncio (and reduces
        # round-trip latency for the user).
        async with self._acquire_conn() as conn:
            while True:
                params = list(base_params)
                clauses: List[str] = []
                if base_where:
                    clauses.append(base_where)
                if last_id is not None:
                    params.append(last_id)
                    clauses.append(f"id > ${len(params)}")
                where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""
                params.append(int(batch_size))
                limit_clause = f" LIMIT ${len(params)}"
                # ``id`` is the tiebreaker so the keyset is unique.
                order_clause = f" ORDER BY {sort_sql}, id ASC"

                sql = (
                    f"SELECT data FROM {schema}.{col}"
                    f"{where_clause}{order_clause}{limit_clause}"
                )
                rows = await conn.fetch(sql, *params)
                if not rows:
                    return
                for row in rows:
                    rec = self._record_from_row(row)
                    yield rec
                    last_id = rec.get("id") or last_id
                if len(rows) < batch_size:
                    return

    # ---- walker traversal (C5) ---------------------------------------------

    async def traverse(
        self,
        edge_collection: str,
        start_id: str,
        *,
        direction: str = "out",
        max_depth: int = 1,
        edge_filter: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Breadth-first walk from ``start_id`` through ``edge_collection``.

        Postgres implements this with a single recursive CTE, collapsing
        what would be N round trips on document backends (one ``find``
        per hop) into one query. The CTE walks edges where
        ``data->>'source'`` (or ``target``, depending on direction) matches
        the current node, expanding to the opposite endpoint at each step.

        Edges are assumed to follow the jvspatial convention: ``data``
        JSONB contains ``"source"`` and ``"target"`` string fields with
        endpoint node IDs.

        Args:
            edge_collection: Collection holding the edge records.
            start_id: Node id to start the walk from.
            direction: ``"out"`` follows ``source -> target``, ``"in"``
                follows ``target -> source``, ``"both"`` walks either
                way at each step.
            max_depth: Maximum hops from ``start_id``. ``1`` returns
                direct neighbors only.
            edge_filter: Optional Mongo-style query applied to the edge
                ``data`` at every hop. Reuses the translator; if any
                portion can't be pushed down the call raises
                ``NotImplementedError`` (callers can fall back to a
                per-hop walk).
            limit: Optional cap on the number of returned hops (post-dedup).

        Returns:
            One dict per discovered (node, edge, depth) triple::

                {"node_id": "...", "edge_id": "...", "depth": N, "parent_id": "..."}

            Results are deduplicated by ``node_id`` keeping the shortest
            depth. ``parent_id`` references the node we arrived from.
            The starting node itself is NOT included.

        Raises:
            ValueError: ``direction`` not in ``{"out", "in", "both"}``;
                ``max_depth`` < 1.
            NotImplementedError: ``edge_filter`` cannot be pushed down to
                SQL — caller should fall back to per-hop iteration.
        """
        if direction not in ("out", "in", "both"):
            raise ValueError(
                f"direction must be 'out', 'in', or 'both', got {direction!r}"
            )
        if max_depth < 1:
            raise ValueError(f"max_depth must be >= 1, got {max_depth}")

        await self._bootstrap_collection(edge_collection)
        col = _safe_collection(edge_collection)
        schema = _safe_collection(self.schema_name)

        # Translate the optional edge filter into a SQL fragment we can
        # AND into both the seed and recursive arms.
        edge_filter_sql = ""
        edge_filter_params: List[Any] = []
        if edge_filter:
            translated = translate_query(edge_filter)
            if translated is None:
                raise NotImplementedError(
                    "PostgresDB.traverse: edge_filter contains operators "
                    "that don't push down to SQL; fall back to per-hop walk"
                )
            edge_filter_sql, edge_filter_params = translated

        # ParamBuilder isn't ideal here because we splice the same params
        # into two arms of the CTE; we keep the raw positional binding.
        # Layout: $1 = start_id, $2 = max_depth, then edge_filter params,
        # then optional $N for the LIMIT.
        params: List[Any] = [str(start_id), int(max_depth)]
        # Shift edge filter placeholders so they refer to params after our
        # first two ($1 / $2). asyncpg requires monotonic $1..$N — we
        # rewrite the translated fragment to bump each placeholder by 2.
        if edge_filter_sql:
            shifted = _shift_placeholders(edge_filter_sql, shift=len(params))
            edge_filter_clause = f" AND ({shifted})"
            params.extend(edge_filter_params)
        else:
            edge_filter_clause = ""

        # Build direction-aware join predicates.
        if direction == "out":
            seed_pred = "(data ->> 'source') = $1"
            seed_next = "data ->> 'target'"
            recur_pred = "(e.data ->> 'source') = walk.node_id"
            recur_next = "e.data ->> 'target'"
        elif direction == "in":
            seed_pred = "(data ->> 'target') = $1"
            seed_next = "data ->> 'source'"
            recur_pred = "(e.data ->> 'target') = walk.node_id"
            recur_next = "e.data ->> 'source'"
        else:  # both
            seed_pred = "((data ->> 'source') = $1 OR (data ->> 'target') = $1)"
            seed_next = (
                "CASE WHEN (data ->> 'source') = $1 "
                "THEN (data ->> 'target') ELSE (data ->> 'source') END"
            )
            recur_pred = (
                "((e.data ->> 'source') = walk.node_id "
                "OR (e.data ->> 'target') = walk.node_id)"
            )
            recur_next = (
                "CASE WHEN (e.data ->> 'source') = walk.node_id "
                "THEN (e.data ->> 'target') ELSE (e.data ->> 'source') END"
            )

        limit_clause = ""
        if limit is not None:
            params.append(int(limit))
            limit_clause = f" LIMIT ${len(params)}"

        sql = f"""
        WITH RECURSIVE walk(node_id, parent_id, edge_id, depth) AS (
            SELECT
                {seed_next} AS node_id,
                $1 AS parent_id,
                id AS edge_id,
                1 AS depth
            FROM {schema}.{col}
            WHERE {seed_pred}{edge_filter_clause}
            UNION ALL
            SELECT
                {recur_next} AS node_id,
                walk.node_id AS parent_id,
                e.id AS edge_id,
                walk.depth + 1 AS depth
            FROM walk
            JOIN {schema}.{col} e ON {recur_pred}
            WHERE walk.depth < $2{edge_filter_clause}
        )
        SELECT DISTINCT ON (node_id) node_id, parent_id, edge_id, depth
        FROM walk
        WHERE node_id IS NOT NULL
        ORDER BY node_id, depth ASC{limit_clause}
        """

        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [
            {
                "node_id": row["node_id"],
                "parent_id": row["parent_id"],
                "edge_id": row["edge_id"],
                "depth": int(row["depth"]),
            }
            for row in rows
        ]

    # ---- transactions ------------------------------------------------------

    async def begin_transaction(self) -> "PostgresTransaction":
        """Open a transactional context backed by an asyncpg connection.

        Returns a :class:`PostgresTransaction` that holds a dedicated
        connection out of the pool for the duration of the transaction.
        The connection is released on commit/rollback. Callers normally
        use :func:`jvspatial.db.transaction.transaction_context` rather
        than calling this directly.
        """
        pool = await self._ensure_pool()
        conn = await pool.acquire()
        txn = conn.transaction()
        await txn.start()
        return PostgresTransaction(self, conn, txn)

    async def commit_transaction(self, transaction: "PostgresTransaction") -> None:
        """Commit ``transaction`` and release its connection back to the pool."""
        await transaction.commit()

    async def rollback_transaction(self, transaction: "PostgresTransaction") -> None:
        """Roll back ``transaction`` and release its connection back to the pool."""
        await transaction.rollback()

    # ---- index management --------------------------------------------------

    async def drop_deprecated_indexes(self, deprecated: Dict[str, List[str]]) -> None:
        """Drop indexes named in ``deprecated`` (collection -> list of names)."""
        if not deprecated:
            return
        pool = await self._ensure_pool()
        schema = _safe_collection(self.schema_name)
        async with pool.acquire() as conn:
            for collection, names in deprecated.items():
                _ = _safe_collection(collection)  # validate even though unused below
                for name in names:
                    if not _SAFE_IDENT_RE.match(name):
                        # Names that fail the PG identifier check (e.g.
                        # Mongo-style ``context.session_id_1`` with dots)
                        # cannot exist as PG indexes — there is nothing
                        # to drop. Log at DEBUG so cross-backend
                        # migrations that share a deprecated-index
                        # registry don't spam WARNING on every boot.
                        logger.debug(
                            "PostgresDB.drop_deprecated_indexes: skipping "
                            "name %r (not a valid PG identifier)",
                            name,
                        )
                        continue
                    try:
                        await conn.execute(f"DROP INDEX IF EXISTS {schema}.{name}")
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.warning(
                            "PostgresDB.drop_deprecated_indexes: %s failed: %s",
                            name,
                            exc,
                        )


# ---- transaction handle -----------------------------------------------------


class PostgresTransaction:
    """Active asyncpg transaction handle.

    Holds a pooled connection + the asyncpg ``Transaction`` object for the
    duration of the transaction. Operations routed through this handle
    bypass the pool and use the held connection so they share the same
    transactional scope. Callers normally interact with this via
    :func:`jvspatial.db.transaction.transaction_context`.

    Lifecycle:
        * created by :meth:`PostgresDB.begin_transaction`
        * released to the pool by :meth:`commit` or :meth:`rollback`
        * idempotent: a second commit / rollback is a no-op

    Args:
        db: Owning :class:`PostgresDB` adapter.
        connection: asyncpg ``Connection`` checked out from the pool.
        transaction: asyncpg ``Transaction`` object already started.
    """

    def __init__(self, db: "PostgresDB", connection: Any, transaction: Any) -> None:
        self._db = db
        self._connection = connection
        self._transaction = transaction
        self.is_active = True
        self.is_committed = False
        self.is_rolled_back = False
        # Surface a unique id so observability layers can correlate.
        import uuid

        self.transaction_id = str(uuid.uuid4())

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert ``data`` into ``collection`` within this transaction."""
        col = _safe_collection(collection)
        schema = _safe_collection(self._db.schema_name)
        await self._db._bootstrap_collection(collection)
        rec_id, entity, tenant, data_json = self._db._split_payload(data)
        await self._connection.execute(
            f"""
            INSERT INTO {schema}.{col} (id, entity, tenant_id, data, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, NOW())
            ON CONFLICT (id) DO UPDATE SET
                entity     = EXCLUDED.entity,
                tenant_id  = EXCLUDED.tenant_id,
                data       = EXCLUDED.data,
                updated_at = NOW()
            """,
            rec_id,
            entity,
            tenant,
            data_json,
        )
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single record by ``id`` from ``collection`` in this transaction."""
        col = _safe_collection(collection)
        schema = _safe_collection(self._db.schema_name)
        await self._db._bootstrap_collection(collection)
        row = await self._connection.fetchrow(
            f"SELECT data FROM {schema}.{col} WHERE id = $1", str(id)
        )
        return self._db._record_from_row(row) if row is not None else None

    async def delete(self, collection: str, id: str) -> bool:
        """Delete record ``id`` from ``collection`` in this transaction."""
        col = _safe_collection(collection)
        schema = _safe_collection(self._db.schema_name)
        await self._db._bootstrap_collection(collection)
        result = await self._connection.execute(
            f"DELETE FROM {schema}.{col} WHERE id = $1", str(id)
        )
        # asyncpg returns "DELETE <n>"; >0 means a row was removed.
        try:
            n = int(result.rsplit(" ", 1)[1])
        except (ValueError, IndexError):
            n = 0
        return n > 0

    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Run ``query`` against ``collection`` within this transaction."""
        col = _safe_collection(collection)
        schema = _safe_collection(self._db.schema_name)
        await self._db._bootstrap_collection(collection)
        translated = translate_query(query) if query else ("", [])
        if translated is None:
            rows = await self._connection.fetch(f"SELECT data FROM {schema}.{col}")
            records = [self._db._record_from_row(r) for r in rows]
            records = [r for r in records if QueryEngine.match(r, query)]
            return finalize_find_results(records, sort=sort, limit=limit)
        where_sql, params = translated
        sort_sql = translate_sort(sort)
        clauses = [where_sql] if where_sql else []
        where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        order_clause = f" ORDER BY {sort_sql}" if sort_sql else ""
        limit_clause = ""
        if limit is not None:
            params = list(params) + [int(limit)]
            limit_clause = f" LIMIT ${len(params)}"
        rows = await self._connection.fetch(
            f"SELECT data FROM {schema}.{col}{where_clause}{order_clause}{limit_clause}",
            *params,
        )
        records = [self._db._record_from_row(r) for r in rows]
        if sort and sort_sql is None:
            records = finalize_find_results(records, sort=sort, limit=None)
        return records

    async def commit(self) -> None:
        """Commit the wrapped asyncpg transaction. Idempotent."""
        if not self.is_active or self.is_committed or self.is_rolled_back:
            return
        try:
            await self._transaction.commit()
            self.is_committed = True
        finally:
            self.is_active = False
            await self._release()

    async def rollback(self) -> None:
        """Roll back the wrapped asyncpg transaction. Idempotent."""
        if not self.is_active or self.is_committed or self.is_rolled_back:
            return
        try:
            await self._transaction.rollback()
            self.is_rolled_back = True
        finally:
            self.is_active = False
            await self._release()

    async def _release(self) -> None:
        if self._connection is None:
            return
        pool = self._db._pool
        if pool is not None:
            try:
                await pool.release(self._connection)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("PostgresTransaction release failed: %s", exc)
        self._connection = None
