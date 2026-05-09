"""Translator: MongoDB-style query dict -> SQLite WHERE clause.

Converts the subset of jvspatial query operators that map cleanly onto
``json_extract`` over our ``data`` JSON column. Anything we don't
understand triggers a graceful fallback: the translator returns ``None``
and the caller loads + filters in Python (the previous behavior).

What we push down
-----------------
* Plain field equality                    ``{"context.name": "alpha"}``
* ``$eq``, ``$ne``                         ``{"x": {"$eq": 1}}``
* ``$gt`` / ``$gte`` / ``$lt`` / ``$lte`` (numbers, strings, bools)
* ``$in`` / ``$nin`` of scalar values      ``{"x": {"$in": [1, 2]}}``
* ``$exists`` true/false
* Top-level multi-field AND (Mongo's implicit AND across fields)
* Explicit ``$and``, ``$or`` (recursive)

What falls back to Python
-------------------------
* ``$regex``, ``$elemMatch``, ``$size``, ``$type``, ``$mod``, ``$where``,
  ``$not``, ``$nor``
* Anything where the operand is a list/dict for an operator that expects a
  scalar
* Field paths containing characters outside ``[A-Za-z0-9_]``
* The internal ``$hint`` and ``$select`` markers added by
  ``QueryEngine.optimize_query``

ORDER BY pushdown
-----------------
:func:`translate_sort` handles single-/multi-key sorts on simple
identifiers (no operators in the key). NULLs sort last for ascending and
first for descending, mirroring the in-memory ``finalize_find_results``
behavior.

Security
--------
Field paths are validated against ``_SAFE_PATH_RE`` before being
interpolated into the SQL string. All values are passed as bound
parameters, never inlined. There's no path through this module that
allows attacker-controlled SQL.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Field-path validator. Allows dot-separated segments of [A-Za-z0-9_].
# Anything else (spaces, quotes, slashes, brackets, dollar signs) is
# rejected and the whole query falls back to Python evaluation.
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# Mapping of supported MongoDB comparators -> SQL operators.
_COMPARATORS = {
    "$eq": "=",
    "$ne": "<>",
    "$gt": ">",
    "$gte": ">=",
    "$lt": "<",
    "$lte": "<=",
}

# Operators we explicitly know we *don't* push down. Their presence in a
# query dict triggers fallback. (Anything not listed here that starts
# with ``$`` also triggers fallback, conservatively.)
_FALLBACK_OPS = {
    "$regex",
    "$options",
    "$elemMatch",
    "$size",
    "$type",
    "$mod",
    "$where",
    "$not",
    "$nor",
    "$all",
    "$text",
}

# Markers QueryEngine.optimize_query may add. We can ignore these and
# still translate the rest of the query.
_IGNORED_TOP_LEVEL = {"$hint", "$select"}


def _safe_field_path(field: str) -> bool:
    """Return True if *field* is safe to interpolate as a JSON path."""
    if not field or field.startswith("$"):
        return False
    return all(_SAFE_SEGMENT_RE.match(seg) for seg in field.split("."))


def _json_extract(field: str) -> str:
    """Return the SQL fragment for ``json_extract(data, '$.field.path')``.

    Caller must have already verified the path with :func:`_safe_field_path`.
    """
    return f"json_extract(data, '$.{field}')"


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _scalar_param(value: Any) -> Any:
    """Coerce a Python scalar to its SQLite parameter form.

    SQLite has no native bool: store as 0/1 to match how Python's
    ``json.dumps`` will have stored it inside the data column.
    """
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def _translate_field_clause(
    field: str, condition: Any
) -> Optional[Tuple[str, List[Any]]]:
    """Translate ``{field: condition}`` for one field.

    Returns ``(sql_fragment, params)`` or ``None`` to signal fallback.
    """
    if not _safe_field_path(field):
        return None

    column = _json_extract(field)

    # Plain equality with a scalar value.
    if not isinstance(condition, dict):
        if not _is_scalar(condition):
            return None
        if condition is None:
            return f"{column} IS NULL", []
        return f"{column} = ?", [_scalar_param(condition)]

    # Operator dict: every key must be one we understand. A mix of
    # supported and unsupported ops on the same field forces fallback.
    fragments: List[str] = []
    params: List[Any] = []
    for op, operand in condition.items():
        if op in _FALLBACK_OPS:
            return None
        if op in _COMPARATORS:
            if not _is_scalar(operand):
                return None
            sql_op = _COMPARATORS[op]
            if operand is None:
                # Mongo equality with None means IS NULL; ne means IS NOT NULL.
                if op == "$eq":
                    fragments.append(f"{column} IS NULL")
                elif op == "$ne":
                    fragments.append(f"{column} IS NOT NULL")
                else:
                    return None
            else:
                # Special handling for $ne so NULL values count as "not equal".
                if op == "$ne":
                    fragments.append(f"({column} IS NULL OR {column} <> ?)")
                else:
                    fragments.append(f"{column} {sql_op} ?")
                params.append(_scalar_param(operand))
            continue
        if op == "$in":
            if not isinstance(operand, (list, tuple)) or not all(
                _is_scalar(v) for v in operand
            ):
                return None
            if not operand:
                # ``x IN ()`` is invalid SQL; an empty $in matches nothing.
                fragments.append("0")
                continue
            placeholders = ",".join("?" * len(operand))
            fragments.append(f"{column} IN ({placeholders})")
            params.extend(_scalar_param(v) for v in operand)
            continue
        if op == "$nin":
            if not isinstance(operand, (list, tuple)) or not all(
                _is_scalar(v) for v in operand
            ):
                return None
            if not operand:
                # Empty $nin matches everything.
                fragments.append("1")
                continue
            placeholders = ",".join("?" * len(operand))
            # Treat NULL as "not in the list" too, matching QueryEngine.
            fragments.append(f"({column} IS NULL OR {column} NOT IN ({placeholders}))")
            params.extend(_scalar_param(v) for v in operand)
            continue
        if op == "$exists":
            if operand:
                fragments.append(f"{column} IS NOT NULL")
            else:
                fragments.append(f"{column} IS NULL")
            continue
        # Unknown operator -> fallback.
        return None

    if not fragments:
        # Empty operator dict is treated as "always true" by Mongo, but
        # this is suspicious enough to fall back rather than silently
        # match every row.
        return None
    return " AND ".join(fragments), params


def _translate_logical(op: str, conditions: Any) -> Optional[Tuple[str, List[Any]]]:
    """Translate ``$and`` / ``$or`` recursively."""
    if not isinstance(conditions, list) or not conditions:
        return None
    parts: List[str] = []
    params: List[Any] = []
    for sub in conditions:
        if not isinstance(sub, dict):
            return None
        translated = translate_query(sub)
        if translated is None:
            return None
        sub_sql, sub_params = translated
        parts.append(f"({sub_sql})")
        params.extend(sub_params)
    joiner = " AND " if op == "$and" else " OR "
    return joiner.join(parts), params


def translate_query(query: Dict[str, Any]) -> Optional[Tuple[str, List[Any]]]:
    """Translate a Mongo-style query dict to ``(sql_where, params)``.

    Returns ``None`` when any portion of the query can't be expressed in
    SQL we trust; the caller should fall back to in-Python filtering.

    The returned SQL fragment is meant to be ANDed into a larger WHERE
    clause; e.g. ``WHERE collection = ? AND (<returned_sql>)``.
    """
    if not query:
        return "", []

    fragments: List[str] = []
    params: List[Any] = []

    for key, value in query.items():
        if key in _IGNORED_TOP_LEVEL:
            continue
        if key in ("$and", "$or"):
            translated = _translate_logical(key, value)
            if translated is None:
                return None
            sub_sql, sub_params = translated
            fragments.append(f"({sub_sql})")
            params.extend(sub_params)
            continue
        if key.startswith("$"):
            # Unknown top-level operator -> fallback.
            return None
        translated = _translate_field_clause(key, value)
        if translated is None:
            return None
        sub_sql, sub_params = translated
        fragments.append(sub_sql)
        params.extend(sub_params)

    if not fragments:
        return "", []
    return " AND ".join(fragments), params


def translate_sort(sort: Optional[List[Tuple[str, int]]]) -> Optional[str]:
    """Translate a sort spec to a SQL ORDER BY fragment.

    Returns ``None`` when the sort can't be expressed (unsafe field name,
    invalid direction). The fragment does NOT include the leading
    ``ORDER BY`` keyword.

    NULLs sort last for ascending, first for descending -- this matches
    ``finalize_find_results`` semantics.
    """
    if not sort:
        return None
    parts: List[str] = []
    for field, direction in sort:
        if direction not in (1, -1):
            return None
        if not _safe_field_path(field):
            return None
        column = _json_extract(field)
        if direction == 1:
            # ascending: NULLs last
            parts.append(f"({column} IS NULL), {column} ASC")
        else:
            # descending: NULLs last too (matches in-memory behavior:
            # the in-memory sort uses (value is None, value), reverse=True,
            # which puts None last because it sorts (True, ...) after
            # (False, ...).)
            parts.append(f"({column} IS NULL), {column} DESC")
    return ", ".join(parts)


__all__ = ["translate_query", "translate_sort"]
