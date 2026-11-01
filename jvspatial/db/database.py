"""Simplified database interface focusing on essential CRUD operations.

This module provides a streamlined database interface that removes
unnecessary complexity while maintaining core functionality.
"""

import base64
import json
import logging
from abc import ABC, abstractmethod
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
from functools import partial
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union

from jvspatial.db.graph_bindings import GraphBindingSummary, LiteralBindingFact
from jvspatial.db.query import QueryEngine


def projection_fields(fields: Any) -> List[str]:
    """Validate and deduplicate literal dotted JSON paths."""
    if not isinstance(fields, (list, tuple)) or not fields:
        raise ValueError("projection fields must be a nonempty list or tuple")
    if any(
        not isinstance(path, str)
        or not path
        or any(not part for part in path.split("."))
        for path in fields
    ):
        raise ValueError("projection paths must contain nonempty segments")
    return list(dict.fromkeys(fields))


def project_record_fields(record: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    """Return flat path/value pairs, preserving explicit null versus missing."""
    result = {}
    for path in fields:
        value = record
        for part in path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            elif (
                isinstance(value, list) and part.isdecimal() and int(part) < len(value)
            ):
                value = value[int(part)]
            else:
                break
        else:
            result[path] = deepcopy(value) if isinstance(value, (dict, list)) else value
    return result


# ---- cursor encoding -------------------------------------------------------

# Opaque bytes that callers pass back to ``find_iter(cursor=...)`` to
# resume a paged iteration. We encode as base64-of-json-of-the-last-row's
# (sort_keys, id) tuple — opaque to the caller, debuggable on demand.


def encode_cursor(payload: Dict[str, Any]) -> bytes:
    """Encode a cursor payload to opaque bytes.

    Format: base64(json(payload)). Stable across backends; callers
    should treat the bytes as fully opaque.
    """
    raw = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw)


def decode_cursor(cursor: Optional[bytes]) -> Optional[Dict[str, Any]]:
    """Decode an opaque cursor produced by :func:`encode_cursor`.

    ``None`` and empty bytes both decode to ``None`` so callers can
    start a fresh iteration without special-casing.
    """
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("cursor payload must be an object")
        return payload
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid cursor: {exc}") from exc


@dataclass(frozen=True)
class BulkSaveResult:
    """Structured outcome of a :meth:`Database.bulk_save_detailed` call.

    Adapters with partial-success semantics (JsonDB, DynamoDB, MongoDB
    ``ordered=False``) report the per-record breakdown so callers can
    distinguish "all saved" from "some lost" — previously every adapter
    returned the same ``int`` and silent drops were indistinguishable
    from success (audit §5.7 / §5.13).
    """

    attempted: int
    saved: int
    failed_ids: List[str] = field(default_factory=list)

    @property
    def all_saved(self) -> bool:
        """Return True when every attempted record persisted."""
        return self.saved == self.attempted and not self.failed_ids


@dataclass(frozen=True)
class InsertIfAbsentResult:
    """Outcome of :meth:`Database.insert_if_absent`.

    ``record`` is the **stored** document (newly inserted or the existing
    winner). ``created`` is ``True`` only when this call performed the
    insert. Never merges proposed fields into an existing row.
    """

    record: Dict[str, Any]
    created: bool


logger = logging.getLogger(__name__)


def resolve_sort_value(record: Dict[str, Any], field: str) -> Any:
    """Read ``field`` out of ``record``, following dotted paths.

    ``field`` may be a plain key (``id``) or a dotted path into nested
    documents (``context.started_at``), matching what the SQLite/Postgres
    sort pushdowns and Mongo's native sort accept. A missing key — or a
    non-dict encountered part-way along the path — resolves to ``None``
    rather than raising, so a malformed record sorts as "missing" instead
    of breaking the whole page.

    Anything that mints or interprets a sort value should go through this
    rather than a flat ``record.get(field)``: cursor payloads in
    :meth:`GraphContext.find_page` and adapter-side sorting must agree on
    what a sort field resolves to.
    """
    if "." not in field:
        return record.get(field)
    value: Any = record
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _find_sort_key(
    record: Dict[str, Any], field: str, *, descending: bool = False
) -> Tuple[bool, Any]:
    """Sort key placing missing values last, ascending or descending.

    Supports dotted paths (``context.started_at``) so callers can sort attribute
    fields the same way they query them. The SQLite/Postgres sort pushdowns
    (``_sqlite_translate.translate_sort`` / ``_postgres_translate.translate_sort``)
    and Mongo's native sort already resolve dotted paths; without this the same
    sort spec silently degraded to "every key is ``None``" whenever a backend
    fell back to the in-memory path.

    ``finalize_find_results`` sorts descending via ``reverse=True``, which flips
    the whole key — including the ``None`` flag. Inverting the flag for
    descending sorts keeps missing values last in both directions, matching the
    ``NULLS LAST`` both SQL translators emit. All missing values share a flag,
    so ``None`` is never compared against a real value.
    """
    value = resolve_sort_value(record, field)
    missing = value is None
    return (not missing if descending else missing, value)


def _normalize_id_query(query: Dict[str, Any]) -> Dict[str, Any]:
    """Map ``_id`` → ``id`` when only ``_id`` is present.

    The default ``find_one_and_update`` / ``find_one_and_delete`` impls
    feed the query into ``QueryEngine.match`` against records stored by
    non-Mongo backends (JsonDB / SQLite / DynamoDB) which only persist
    ``id``. Callers that follow the Mongo-style convention of querying
    by ``_id`` would otherwise silently miss every row on those backends
    (audit §5.3). When both keys are present the caller's intent is
    preserved verbatim.
    """
    if "_id" in query and "id" not in query:
        normalized = {k: v for k, v in query.items() if k != "_id"}
        normalized["id"] = query["_id"]
        return normalized
    return query


def finalize_find_results(
    records: List[Dict[str, Any]],
    *,
    sort: Optional[List[Tuple[str, int]]] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Apply optional Mongo-style sort and limit in memory.

    ``sort`` is a list of ``(field, direction)`` with ``direction`` ``1`` for
    ascending and ``-1`` for descending. Sorting is stable; compound sorts are
    applied from the last key to the first. Records missing the sort field sort
    last in both directions, matching the ``NULLS LAST`` the SQLite and Postgres
    pushdowns emit.
    """
    out = records
    if sort:
        out = list(records)
        for sort_field, direction in reversed(sort):
            descending = direction == -1
            out.sort(
                key=partial(_find_sort_key, field=sort_field, descending=descending),
                reverse=descending,
            )
    if limit is not None:
        out = out[:limit]
    return out


# Context-local execution metadata; wrappers read the result of their own call.
_query_execution: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "jvspatial_query_execution", default=None
)

_io_metrics: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "jvspatial_io_metrics", default=None
)


def _record_io_metric(name: str, value: float = 1) -> None:
    """Accumulate only inside an observed call; no shared adapter state."""
    metrics = _io_metrics.get()
    if metrics is not None:
        metrics[name] = metrics.get(name, 0) + value


def _record_decoded_bytes(value: Any) -> None:
    if _io_metrics.get() is not None:
        raw = value.encode() if isinstance(value, str) else json.dumps(value).encode()
        _record_io_metric("decoded_bytes", len(raw))


def _pushdown_conjuncts(query: Dict[str, Any], translator: Any) -> Dict[str, Any]:
    """Extract safe AND predicates, never pieces of an OR/NOT expression.

    The original predicate must still be evaluated on every candidate.
    """
    if translator(query) is not None:
        return query
    supported = []
    for key, value in query.items():
        if key == "$and" and isinstance(value, list):
            for child in value:
                if isinstance(child, dict):
                    part = _pushdown_conjuncts(child, translator)
                    if part:
                        supported.append(part)
        elif (
            not key.startswith("$")
            and isinstance(value, dict)
            and any(k.startswith("$") for k in value)
        ):
            if translator({key: value}) is not None:
                supported.append({key: value})
                continue
            for op, operand in value.items():
                if op == "$options":
                    continue
                clause = {op: operand}
                if op == "$regex" and "$options" in value:
                    clause["$options"] = value["$options"]
                part = {key: clause}
                if translator(part) is not None:
                    supported.append(part)
        elif translator({key: value}) is not None:
            supported.append({key: value})
    return {"$and": supported} if supported else {}


def _validate_scan_limit(value: Optional[int]) -> Optional[int]:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value < 0
    ):
        raise ValueError("fallback_scan_limit must be a nonnegative integer or None")
    return value


def _keyset_sort_fields(
    sort: Optional[List[Tuple[str, int]]],
) -> List[Tuple[str, int]]:
    """Validate a deterministic order, retaining the existing ID tiebreaker."""
    fields = list(sort) if sort else [("id", 1)]
    seen = set()
    for name, direction in fields:
        if not isinstance(name, str) or not name or direction not in (1, -1):
            raise ValueError("sort fields require a name and direction 1 or -1")
        if name in seen:
            raise ValueError("sort fields must be unique")
        seen.add(name)
    if "id" not in seen:
        fields.append(("id", fields[0][1]))
    return fields


def _keyset_payload(
    record: Dict[str, Any], fields: List[Tuple[str, int]]
) -> Dict[str, Any]:
    """Capture every ordering value; the legacy primary value remains readable."""
    if record.get("id") is None:
        raise ValueError("keyset iteration requires a record id")
    values = [resolve_sort_value(record, name) for name, _ in fields]
    return {
        "id": record["id"],
        "sort": values[0],
        "values": values,
        "fields": [list(item) for item in fields],
    }


def _keyset_condition(
    fields: List[Tuple[str, int]],
    payload: Optional[Dict[str, Any]],
    *,
    nulls_first: bool = False,
) -> Optional[Dict[str, Any]]:
    """Lexicographic continuation, including null runs and mixed directions.

    SQL and in-memory sorts place nulls last. Mongo's native ascending
    sort places them first, selected explicitly by its adapter.
    """
    if payload is None:
        return None
    if "id" not in payload:
        raise ValueError("cursor requires an id")
    if "fields" in payload and payload["fields"] != [list(f) for f in fields]:
        raise ValueError("cursor sort does not match requested sort")
    values = payload.get("values")
    if values is None:
        if len(fields) == 1 and fields[0][0] == "id":
            values = [payload["id"]]
        elif len(fields) == 2 and fields[-1][0] == "id" and "sort" in payload:
            values = [payload["sort"], payload["id"]]
        else:
            raise ValueError("composite sort cursor requires all sort values")
    if not isinstance(values, list) or len(values) != len(fields):
        raise ValueError("cursor values do not match requested sort")
    branches: List[Dict[str, Any]] = []
    prefix: List[Dict[str, Any]] = []
    after: Optional[Dict[str, Any]]
    for (name, direction), value in zip(fields, values):
        missing_first = nulls_first and direction == 1
        if value is None:
            after = {name: {"$ne": None}} if missing_first else None
        else:
            comparison: Dict[str, Any] = {
                name: {"$lt" if direction < 0 else "$gt": value}
            }
            after = (
                comparison
                if missing_first or name == "id"
                else {"$or": [comparison, {name: None}]}
            )
        if after is not None:
            branches.append({"$and": [*prefix, after]} if prefix else after)
        prefix.append({name: value})
    # ID is non-null and unique, so a nonempty branch always exists.
    return {"$or": branches}


class Database(ABC):
    """Simplified abstract base class for database adapters.

    Provides essential CRUD operations without complex transaction support.
    Focuses on core functionality.

    All implementations must support:
    - Basic CRUD operations (save, get, delete, find)
    - Collection-based data organization
    - Simple query operations with dict-based filters

    **Standard compound operations** (always available on built-in adapters):

    - ``find_one_and_update`` — default uses ``find_one`` + ``QueryEngine.apply_update``
      + ``save`` (read-modify-write; **not** atomic under concurrency except where
      overridden, e.g. MongoDB native).
    - ``find_one_and_delete`` — default uses ``find_one`` + ``delete`` (not atomic
      except MongoDB native override).

    Query matching for both follows the same rules as :meth:`find_one` / :meth:`find`
    (Mongo-style operators via :class:`~jvspatial.db.query.QueryEngine` where the
    adapter applies it).

    Capability flags
    ----------------
    Subclasses set the following class attributes so callers can branch on
    capabilities without sniffing for adapter classes:

    ``supports_transactions``
        ``True`` if :meth:`begin_transaction` returns a real transaction
        with ACID semantics (e.g. MongoDB replica set). ``False`` for
        adapters where transactions are unavailable or only available in a
        weak buffered form. Default ``False``.
    """

    # Capability flags. Override in subclasses.
    supports_transactions: bool = False
    supports_native_graph_paging: bool = False

    @property
    def supports_native_projected_reads(self) -> bool:
        """Whether projection is performed natively by the current adapter."""
        return False

    @property
    def supports_native_graph_binding_summary(self) -> bool:
        """Whether the current adapter provides native graph fact summaries."""
        return False

    async def graph_node_batch(self, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch raw projection nodes; wrappers bypass stale record caches."""
        return await self.find_many("node", ids)

    async def graph_edge_page(
        self, node_id: str, *, after: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Page incident edges deterministically by ID, without exact counts.

        Native-capable adapters must push this fixed query, sort, and limit to
        storage. Other adapters provide a disclosed scan-based compatibility
        implementation. This capability bounds returned rows, not physical scan
        work. Custom adapters may override the method and capability together.
        """
        if limit < 1 or limit > 500:
            raise ValueError("graph edge page limit must be between 1 and 500")
        incident: Dict[str, Any] = {"$or": [{"source": node_id}, {"target": node_id}]}
        query = {"$and": [incident, {"id": {"$gt": after}}]} if after else incident
        return await self.find("edge", query, sort=[("id", 1)], limit=limit)

    @abstractmethod
    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database.

        Args:
            collection: Collection name
            data: Record data

        Returns:
            Saved record with any database-generated fields
        """
        pass

    @staticmethod
    def _validate_insert_if_absent(data: Dict[str, Any], conflict_target: str) -> str:
        """Validate v1 ``insert_if_absent`` arguments; return the record id.

        Raises:
            ValueError: ``conflict_target`` is not ``'id'``, or ``data``
                lacks a non-empty ``id``.
        """
        if conflict_target != "id":
            raise ValueError(
                "insert_if_absent conflict_target must be 'id' in v1; "
                f"got {conflict_target!r}"
            )
        if not data or data.get("id") is None or data.get("id") == "":
            raise ValueError(
                "insert_if_absent requires data with a non-empty 'id' field"
            )
        return str(data["id"])

    async def insert_if_absent(
        self,
        collection: str,
        data: Dict[str, Any],
        *,
        conflict_target: str = "id",
    ) -> InsertIfAbsentResult:
        """Insert ``data`` only when no row exists for ``conflict_target``.

        v1 supports ``conflict_target='id'`` (primary key) only. On
        conflict, returns the **existing stored** record unchanged
        (``created=False``). Must not call through :meth:`save`.

        Built-in adapters override this with an atomic backend primitive.
        The default raises :class:`NotImplementedError` after validation
        so custom adapters fail loudly until they implement it.

        Args:
            collection: Collection name
            data: Record data (must include non-empty ``id``)
            conflict_target: Conflict key; must be ``'id'`` in v1

        Returns:
            :class:`InsertIfAbsentResult` with the stored record and
            whether this call created it

        Raises:
            ValueError: Invalid ``conflict_target`` or missing ``id``
            NotImplementedError: Adapter has not implemented this method
        """
        self._validate_insert_if_absent(data, conflict_target)
        raise NotImplementedError(
            f"{type(self).__name__} does not implement insert_if_absent"
        )

    @abstractmethod
    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID.

        Args:
            collection: Collection name
            id: Record ID

        Returns:
            Record data or None if not found
        """
        pass

    @abstractmethod
    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID.

        Args:
            collection: Collection name
            id: Record ID
        """
        pass

    @abstractmethod
    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Find records matching a query.

        Args:
            collection: Collection name
            query: Query parameters (empty dict for all records)
            limit: Optional maximum number of documents to return after matching
            sort: Optional list of ``(field, direction)`` tuples (``1`` asc, ``-1`` desc)

        Returns:
            List of matching records

        Ordering contract (SPEC §4.1) — implementations must satisfy all of
        it whether they push the sort into the backend or fall back to
        :func:`finalize_find_results`:

        * ``field`` may be a dotted path into nested documents
          (``context.started_at``); resolve it with
          :func:`resolve_sort_value`, never a flat ``record.get(field)``.
        * Records with no value for the sort field come **last in both
          directions**, matching the ``NULLS LAST`` the SQL translators emit.
        * The sort is stable; compound sorts apply from the last key first.
        * If the ordering cannot be expressed in the backend, ``limit`` must
          not be pushed down either — fetch the full match set and apply
          ``sort`` and ``limit`` together in memory, or the result is the top
          N of an arbitrary N.

        Known divergences are listed in SPEC §4.1 (MongoDB places missing
        values first on ascending sorts; heterogeneous value types raise in
        memory but order by storage class in SQL).
        """
        pass

    async def count_incident_edges(
        self, collection: str, node_ids: List[str]
    ) -> Dict[str, int]:
        """Count each edge once per endpoint, including self-loops once."""
        counts = dict.fromkeys(node_ids, 0)
        if not counts:
            return counts
        query = {
            "$or": [
                {"source": {"$in": list(counts)}},
                {"target": {"$in": list(counts)}},
            ]
        }
        iterator = self.find_iter(collection, query)
        try:
            async for edge in iterator:
                for nid in {
                    value
                    for value in (edge.get("source"), edge.get("target"))
                    if isinstance(value, str)
                }:
                    if nid in counts:
                        counts[nid] += 1
        finally:
            close = getattr(iterator, "aclose", None)
            if callable(close):
                await close()
        return counts

    async def find_ids(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
        offset: int = 0,
    ) -> List[str]:
        """Return only IDs for raw paging/export; adapters may project natively.

        Offset paging still examines a prefix in the store, but native
        implementations do not transfer discarded full documents. This
        fallback preserves correctness for third-party adapters.
        """
        if offset < 0 or (limit is not None and limit < 0):
            raise ValueError("offset and limit must be nonnegative")
        rows = await self.find(
            collection,
            query,
            sort=_keyset_sort_fields(sort),
            limit=None if limit is None else offset + limit,
        )
        return [str(r["id"]) for r in rows[offset:]]

    async def count(
        self, collection: str, query: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count records matching a query.

        Args:
            collection: Collection name
            query: Query parameters (empty dict for all records)

        Returns:
            Number of matching records
        """
        if query is None:
            query = {}
        results = await self.find(collection, query)
        return len(results)

    async def summarize_graph_bindings(
        self,
        query: Dict[str, Any],
        *,
        record_entity: str,
        edge_entity: str,
        parent_id: str,
        facts: Tuple[LiteralBindingFact, ...],
        max_records: int = 100000,
        max_edges: int = 400000,
    ) -> Optional[GraphBindingSummary]:
        """Optional native fact aggregate; None means use the caller's fallback.

        This does not authorize any read. A consuming host must prove its
        principal, current scope and rooted parent independently. It must never
        use an incomplete result as an exact count, or silently discard invalid
        authority facts. Unsupported adapters retain their established executor.
        """
        return None

    async def find_projected(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        fields: List[str],
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Read flat dotted-path projections after complete filtering/ordering.

        Missing paths are omitted; explicit nulls remain. Returned maps are
        projections, not complete persistence records or hydrated entities.
        Adapters may push projection down only when filtering and ordering
        semantics are preserved. The portable fallback projects after find().
        """
        names = projection_fields(fields)
        return [
            project_record_fields(row, names)
            for row in await self.find(collection, query, limit=limit, sort=sort)
        ]

    async def find_iter(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        sort: Optional[List[Tuple[str, int]]] = None,
        batch_size: int = 100,
        cursor: Optional[bytes] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Iterate in deterministic composite order with an ID tiebreaker.

        ``batch_size`` is a positive integer. The generic pager retains one
        page; an adapter fallback may still need to sort all matches. Cursors
        track every sort field and direction. Mongo uses native BSON null
        ordering; SQL and in-memory sorts place missing/null last.

        This is live pagination, not a repeatable-read snapshot. Inserts before
        the cursor are not visited; sort-key updates can skip or revisit rows.
        Use an explicit transaction/snapshot if exactly-once reads are needed.
        An id-only cursor remains valid for an id-only sort. Custom-sort
        checkpoints require all sort values, as GraphContext.find_page emits.
        """
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or batch_size < 1
        ):
            raise ValueError("batch_size must be a positive integer")
        fields = _keyset_sort_fields(sort)
        payload = decode_cursor(cursor)
        while True:
            after = _keyset_condition(
                fields, payload, nulls_first=getattr(self, "_keyset_nulls_first", False)
            )
            page_query = (
                ({"$and": [query, after]} if query else after)
                if after is not None
                else dict(query)
            )
            results = await self.find(
                collection, page_query, sort=fields, limit=batch_size
            )
            if not results:
                return
            for rec in results:
                payload = _keyset_payload(rec, fields)
                yield rec
            if len(results) < batch_size:
                return

    async def find_one(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find the first record matching a query.

        Args:
            collection: Collection name
            query: Query parameters

        Returns:
            First matching record or None if not found
        """
        results = await self.find(collection, query, limit=1)
        return results[0] if results else None

    async def find_many(
        self, collection: str, ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Bulk-fetch records by id in one round trip per backend.

        Args:
            collection: Collection name.
            ids: Record IDs to fetch. Duplicates are de-duplicated.

        Returns:
            ``{id: record}`` for each id that exists. Missing ids are
            simply absent from the result (no exception, no ``None``
            placeholder). Order is **not** preserved across backends --
            iterate the returned dict by your input ``ids`` list if you
            need stable ordering.

        Performance:
            * MongoDB: single ``find({"_id": {"$in": ids}})`` call.
            * SQLite: single ``WHERE collection=? AND id IN (?,?,...)`` SELECT.
            * DynamoDB: chunked ``BatchGetItem`` (100 ids/request) with
              parallel batches.
            * JsonDB: parallel ``asyncio.gather`` over per-file reads.

            The default implementation in this base class issues N
            sequential ``get()`` calls -- adapters should override.
        """
        if not ids:
            return {}
        unique_ids = list(dict.fromkeys(ids))  # de-dup, preserve order
        out: Dict[str, Dict[str, Any]] = {}
        for rec_id in unique_ids:
            doc = await self.get(collection, rec_id)
            if doc is not None:
                out[rec_id] = doc
        return out

    async def bulk_save(self, collection: str, records: List[Dict[str, Any]]) -> int:
        """Save many records in one round trip per backend.

        Args:
            collection: Collection name.
            records: Iterable of record dicts. Each must have an ``id``
                field. Records without ``id`` raise ``ValueError``.

        Returns:
            Number of records successfully saved.

        For partial-success visibility (which IDs failed) use
        :meth:`bulk_save_detailed`. Adapters with all-or-nothing
        semantics (SQLite) raise rather than return a partial count.
        """
        result = await self.bulk_save_detailed(collection, records)
        return result.saved

    async def bulk_save_detailed(
        self, collection: str, records: List[Dict[str, Any]]
    ) -> BulkSaveResult:
        """Save many records, returning a structured per-record outcome.

        Args:
            collection: Collection name.
            records: Iterable of record dicts. Each must have an ``id``
                field. Records without ``id`` raise ``ValueError`` (the
                check is per-batch, before any save attempt).

        Returns:
            :class:`BulkSaveResult` with ``attempted`` / ``saved`` /
            ``failed_ids``.

        Atomicity (per backend):
            * MongoDB: ``bulk_write`` with ``ordered=False`` — partial
              successes are reported; failures don't block other writes.
            * SQLite: single transaction with ``executemany``; **all
              records or none** land. A constraint violation rolls back
              the whole batch and raises (``failed_ids`` is unset).
            * DynamoDB: ``BatchWriteItem`` with unprocessed-item retry;
              unprocessed items after retries land in ``failed_ids``.
            * JsonDB: parallel atomic per-file writes; per-record
              exceptions land in ``failed_ids``.

            The default implementation in this base class is a serial
            loop of ``save()`` calls catching per-record exceptions.
            Adapters should override for round-trip efficiency.
        """
        if not records:
            return BulkSaveResult(attempted=0, saved=0, failed_ids=[])
        for idx, r in enumerate(records):
            if "id" not in r:
                # Caller error — surface the offending index for fast
                # debugging (audit §5.15).
                raise ValueError(f"bulk_save: record at index {idx} has no 'id' field")

        saved = 0
        failed_ids: List[str] = []
        for r in records:
            try:
                await self.save(collection, dict(r))
                saved += 1
            except Exception as e:  # pragma: no cover — defensive
                logger.warning(
                    "%s.bulk_save: record id=%r failed: %s",
                    type(self).__name__,
                    r.get("id"),
                    e,
                )
                failed_ids.append(str(r.get("id", "")))
        return BulkSaveResult(
            attempted=len(records), saved=saved, failed_ids=failed_ids
        )

    async def find_one_and_delete(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find and delete the first record matching ``query``.

        **Query semantics** match :meth:`find_one` (same dict filters and operators
        supported by the adapter, typically via :class:`~jvspatial.db.query.QueryEngine`).

        **Atomicity:** the default implementation is ``find_one`` then ``delete`` and is
        **not** atomic under concurrent writers. MongoDB overrides with a native
        ``find_one_and_delete`` for atomicity.

        Args:
            collection: Collection name
            query: Query parameters (e.g. ``{"_id": "x", "_jv_claim": "token"}``)

        Returns:
            Deleted document if found, ``None`` otherwise
        """
        # Non-Mongo backends store records keyed by ``id`` only. Normalize
        # the Mongo-style ``_id`` filter so default matching works
        # uniformly (audit §5.3 / SPEC §4.1).
        doc = await self.find_one(collection, _normalize_id_query(query))
        if doc is None:
            return None
        record_id = doc.get("_id", doc.get("id"))
        if record_id is not None:
            await self.delete(collection, str(record_id))
        return doc

    async def find_one_and_update(
        self,
        collection: str,
        query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Find and update the first record matching ``query``.

        Default implementation: ``find_one`` + ``QueryEngine.apply_update`` + ``save``.
        **Not atomic** under concurrent writers (MongoDB overrides with native
        ``find_one_and_update``).

        Supported update operators include ``$set``, ``$unset``, ``$inc``, ``$push``,
        ``$addToSet``, and ``$setOnInsert`` when ``upsert=True``.

        Args:
            collection: Collection name
            query: Query parameters (e.g. ``{"_id": "sender_id"}``)
            update: MongoDB-style update document
            upsert: If ``True``, create a document when no match

        Returns:
            Updated document, or ``None`` if no match and ``upsert`` is ``False``
        """
        # Non-Mongo backends store records keyed by ``id`` only. Normalize
        # the Mongo-style ``_id`` filter so default matching works
        # uniformly (audit §5.3 / SPEC §4.1).
        normalized = _normalize_id_query(query)
        doc = await self.find_one(collection, normalized)
        is_new = doc is None
        if is_new:
            if not upsert:
                return None
            doc = {}
            doc_id = query.get("_id", query.get("id"))
            if doc_id is not None:
                doc["_id"] = doc_id
                doc["id"] = str(doc_id)
            QueryEngine.apply_update(doc, update, apply_set_on_insert=True)
        else:
            QueryEngine.apply_update(doc, update, apply_set_on_insert=False)

        record_id = doc.get("id", doc.get("_id"))
        if record_id is not None:
            doc["id"] = str(record_id)
        await self.save(collection, doc)
        return doc

    async def create_index(
        self,
        collection: str,
        field_or_fields: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        **kwargs: Any,
    ) -> None:
        """Create an index on the specified field(s).

        This is an optional method that databases can implement for performance optimization.
        Databases that don't support indexing should override this with a no-op implementation.

        Args:
            collection: Collection name
            field_or_fields: Single field name (str) or list of (field_name, direction) tuples for compound indexes
            unique: Whether the index should enforce uniqueness
            **kwargs: Additional database-specific index options (e.g., expireAfterSeconds for TTL indexes)

        Note:
            Default implementation logs a warning. Database implementations should override this method.
        """
        logger.warning(
            f"create_index() called on {self.__class__.__name__} but indexing is not implemented. "
            f"Index creation for collection '{collection}' on field(s) '{field_or_fields}' was ignored."
        )

    async def drop_deprecated_indexes(self, deprecated: Dict[str, List[str]]) -> None:
        """Drop indexes that were removed or renamed in code (orphan cleanup).

        Called once at startup with a map of collection name → list of old index
        names to remove.  The default implementation is a no-op so that adapters
        which do not use named indexes (e.g. in-memory) can ignore it.

        Adapters that do support named indexes (MongoDB, PostgreSQL with explicit
        index names, etc.) should override this to silently skip missing indexes
        and log a warning for any other errors.

        Args:
            deprecated: Mapping of collection name to old index names.
                        Example: ``{"node": ["conv_id_only", "context.session_id_1"]}``
        """
        return None


__all__ = [
    "Database",
    "DatabaseError",
    "VersionConflictError",
    "BulkSaveResult",
    "InsertIfAbsentResult",
    "encode_cursor",
    "decode_cursor",
    "finalize_find_results",
    "resolve_sort_value",
]


class DatabaseError(Exception):
    """Base exception for database operations."""

    pass


class VersionConflictError(DatabaseError):
    """Raised when a document version conflict occurs during update."""

    pass
