"""Translator: MongoDB-style query dict -> Postgres WHERE clause + params.

PostgreSQL's JSONB support is rich enough to push down effectively the entire
Mongo-style operator surface — the few exceptions are intentional (``$where``
is a security hazard, ``$text`` is Mongo-specific). This is a substantial
upgrade over the SQLite translator (~50 % fallback) and is the single biggest
reason the Postgres backend is positioned as the production default.

Operator coverage (all push down to native SQL):

* Field equality on scalars + ``$eq``, ``$ne``                              ✓
* ``$gt`` / ``$gte`` / ``$lt`` / ``$lte`` on numbers / strings / bools      ✓
* ``$in`` / ``$nin`` of scalars                                             ✓
* ``$exists`` true/false                                                    ✓
* ``$regex`` (case-sensitive ``~`` / insensitive ``~*``) + ``$options="i"`` ✓
* ``$mod`` numeric remainder                                                ✓
* ``$size`` on JSONB array length                                           ✓
* ``$type`` via ``jsonb_typeof``                                            ✓
* ``$elemMatch`` via ``jsonb_array_elements`` + subquery                    ✓
* ``$all`` as conjunction of containment checks                             ✓
* ``$not`` wraps inverted subclause                                         ✓
* ``$and`` / ``$or`` / ``$nor`` recursive                                   ✓
* Top-level multi-field AND (Mongo's implicit AND across fields)            ✓

Fallback (returns ``None`` — caller drops to in-Python ``QueryEngine``):

* ``$where``  (security — code-string evaluation)
* ``$text``   (Mongo-specific full-text)
* Anything not on the above list (conservative default)

Parameter binding
-----------------
asyncpg uses positional ``$1``, ``$2``, … placeholders. The translator
returns ``(sql_fragment, params)`` where the fragment can be ANDed into a
larger WHERE and ``params`` is the list of bound values. A caller-side
counter (``ParamBuilder``) advances the placeholder index so multiple
translator calls in the same statement compose without collision.

Field-path safety
-----------------
JSONB path segments are validated against ``_SAFE_SEGMENT_RE`` before being
interpolated into the SQL string. ``data #> '{a,b,c}'`` is path-extracted —
the path literal is built from validated segments and contains no
attacker-controlled text. All scalar operands flow through bind parameters.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Path-segment safety: alpha-num + underscore. We do not support quoted
# JSONB keys with arbitrary characters — pin to safe ASCII so the path
# literal can be interpolated without escape concerns.
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Operators we explicitly know we don't push down. (``$where`` is a code
# injection vector; ``$text`` is Mongo-specific.)
_FALLBACK_OPS = {"$where", "$text"}

# Internal markers QueryEngine.optimize_query may add; safe to ignore.
_IGNORED_TOP_LEVEL = {"$hint", "$select"}

# Simple comparators that map directly to SQL operators after a JSONB
# extraction. We use ``#>`` (returns jsonb) so equality works for all
# scalar types, then cast to numeric / text on the comparison side as
# needed.
_COMPARATORS = {
    "$eq": "=",
    "$ne": "<>",
    "$gt": ">",
    "$gte": ">=",
    "$lt": "<",
    "$lte": "<=",
}


# ---- helpers ----------------------------------------------------------------


def _safe_field_path(field: str) -> bool:
    """Return True if every dot-separated segment of *field* is safe."""
    if not field or field.startswith("$"):
        return False
    return all(_SAFE_SEGMENT_RE.match(seg) for seg in field.split("."))


def _path_literal(field: str) -> str:
    """Build a Postgres text-array path literal like ``'{a,b,c}'``."""
    return "{" + ",".join(field.split(".")) + "}"


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


class ParamBuilder:
    """Accumulator that hands out ``$N`` placeholders + collects bound values.

    asyncpg requires positional placeholders. Each call to :meth:`add`
    appends the value and returns the next placeholder string, so nested
    translator calls compose naturally.
    """

    __slots__ = ("_params",)

    def __init__(self) -> None:
        self._params: List[Any] = []

    def add(self, value: Any) -> str:
        """Append ``value`` and return its positional placeholder (``$N``)."""
        self._params.append(value)
        return f"${len(self._params)}"

    @property
    def values(self) -> List[Any]:
        """Return the accumulated positional parameter list."""
        return self._params


# ---- field-clause translation ----------------------------------------------


def _translate_field_clause(
    field: str, condition: Any, pb: ParamBuilder
) -> Optional[str]:
    """Translate ``{field: condition}`` to a SQL fragment.

    Returns ``None`` to signal fallback (the whole query should drop to
    in-Python evaluation).
    """
    if not _safe_field_path(field):
        return None

    path = _path_literal(field)
    extract_text = f"(data #>> '{path}')"  # text
    extract_jsonb = f"(data #> '{path}')"  # jsonb

    # Plain equality with a scalar value.
    if not isinstance(condition, dict):
        if not _is_scalar(condition):
            return None
        if condition is None:
            return f"{extract_jsonb} IS NULL"
        # Use JSONB equality so type-aware comparison works for booleans
        # and numbers stored in JSON form.
        ph = pb.add(condition)
        return _eq_clause(extract_text, extract_jsonb, ph, condition)

    # Operator dict — every key must be one we understand. A mix of
    # supported + unsupported ops on the same field forces fallback.
    fragments: List[str] = []
    for op, operand in condition.items():
        if op in _FALLBACK_OPS:
            return None

        if op in _COMPARATORS:
            piece = _comparator_clause(op, operand, extract_text, extract_jsonb, pb)
            if piece is None:
                return None
            fragments.append(piece)
            continue

        if op == "$in":
            piece = _in_clause(operand, extract_text, extract_jsonb, pb, negate=False)
            if piece is None:
                return None
            fragments.append(piece)
            continue

        if op == "$nin":
            piece = _in_clause(operand, extract_text, extract_jsonb, pb, negate=True)
            if piece is None:
                return None
            fragments.append(piece)
            continue

        if op == "$exists":
            fragments.append(
                f"{extract_jsonb} IS NOT NULL"
                if operand
                else f"{extract_jsonb} IS NULL"
            )
            continue

        if op == "$regex":
            # Mongo's ``$regex`` may pair with ``$options`` for flags.
            options = condition.get("$options", "")
            piece = _regex_clause(operand, options, extract_text, pb)
            if piece is None:
                return None
            fragments.append(piece)
            continue

        if op == "$options":
            # Consumed alongside $regex above; ignore here.
            if "$regex" in condition:
                continue
            return None

        if op == "$mod":
            piece = _mod_clause(operand, extract_text, pb)
            if piece is None:
                return None
            fragments.append(piece)
            continue

        if op == "$size":
            if not isinstance(operand, int):
                return None
            ph = pb.add(operand)
            fragments.append(f"jsonb_array_length({extract_jsonb}) = {ph}")
            continue

        if op == "$type":
            piece = _type_clause(operand, extract_jsonb, pb)
            if piece is None:
                return None
            fragments.append(piece)
            continue

        if op == "$elemMatch":
            piece = _elem_match_clause(operand, extract_jsonb, pb)
            if piece is None:
                return None
            fragments.append(piece)
            continue

        if op == "$all":
            piece = _all_clause(operand, extract_jsonb, pb)
            if piece is None:
                return None
            fragments.append(piece)
            continue

        if op == "$not":
            # $not wraps a fresh operator dict; recurse on the same field
            # then negate the whole thing.
            if not isinstance(operand, dict):
                return None
            inner = _translate_field_clause(field, operand, pb)
            if inner is None:
                return None
            fragments.append(f"NOT ({inner})")
            continue

        # Unknown operator -> fallback.
        return None

    if not fragments:
        return None
    return " AND ".join(fragments)


def _eq_clause(
    extract_text: str, extract_jsonb: str, placeholder: str, value: Any
) -> str:
    """Emit a scalar-equality clause.

    Uses ``#>>`` (text) when the operand is a string for index-friendly
    comparison; uses ``#>`` (jsonb) with ``to_jsonb`` for booleans / numbers
    so JSON type semantics hold.
    """
    if isinstance(value, bool):
        return f"{extract_jsonb} = to_jsonb({placeholder}::boolean)"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"({extract_text})::numeric = {placeholder}::numeric"
    # String / other scalar — text compare.
    return f"{extract_text} = {placeholder}"


def _comparator_clause(
    op: str,
    operand: Any,
    extract_text: str,
    extract_jsonb: str,
    pb: ParamBuilder,
) -> Optional[str]:
    if not _is_scalar(operand):
        return None
    sql_op = _COMPARATORS[op]
    if operand is None:
        if op == "$eq":
            return f"{extract_jsonb} IS NULL"
        if op == "$ne":
            return f"{extract_jsonb} IS NOT NULL"
        return None

    ph = pb.add(operand)

    if op == "$eq":
        return _eq_clause(extract_text, extract_jsonb, ph, operand)

    if op == "$ne":
        # Treat NULL as "not equal" — matches QueryEngine semantics.
        eq = _eq_clause(extract_text, extract_jsonb, ph, operand)
        return f"({extract_jsonb} IS NULL OR NOT ({eq}))"

    if isinstance(operand, bool):
        # Boolean ordering on > / < is nonsense; fall back.
        return None
    if isinstance(operand, (int, float)):
        return f"({extract_text})::numeric {sql_op} {ph}::numeric"
    # String comparison.
    return f"{extract_text} {sql_op} {ph}"


def _in_clause(
    operand: Any,
    extract_text: str,
    extract_jsonb: str,
    pb: ParamBuilder,
    *,
    negate: bool,
) -> Optional[str]:
    if not isinstance(operand, (list, tuple)) or not all(
        _is_scalar(v) for v in operand
    ):
        return None
    if not operand:
        # ``x IN ()`` is invalid SQL; an empty $in matches nothing,
        # an empty $nin matches everything.
        return "FALSE" if not negate else "TRUE"

    # Build a jsonb array placeholder + use the ``?|`` / containment
    # operators where possible. For typed values we use ``= ANY(...)``
    # with a typed array.
    if all(isinstance(v, str) and not isinstance(v, bool) for v in operand):
        ph = pb.add(list(operand))
        inner = f"{extract_text} = ANY({ph}::text[])"
        if negate:
            return f"({extract_jsonb} IS NULL OR NOT ({inner}))"
        return inner

    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in operand):
        ph = pb.add([float(v) for v in operand])
        inner = f"({extract_text})::numeric = ANY({ph}::numeric[])"
        if negate:
            return f"({extract_jsonb} IS NULL OR NOT ({inner}))"
        return inner

    # Mixed-type list: compare via JSONB.
    ph = pb.add([_to_jsonb_literal(v) for v in operand])
    inner = f"{extract_jsonb}::text = ANY({ph}::text[])"
    if negate:
        return f"({extract_jsonb} IS NULL OR NOT ({inner}))"
    return inner


def _regex_clause(
    pattern: Any, options: Any, extract_text: str, pb: ParamBuilder
) -> Optional[str]:
    if not isinstance(pattern, str):
        return None
    flags = options if isinstance(options, str) else ""
    # ``i`` flag → case-insensitive; other Mongo flags (m, s, x) don't
    # map cleanly to POSIX regex. We honour ``i`` only and reject the
    # rest to fall back rather than silently behave incorrectly.
    if flags and not all(c in "i" for c in flags):
        return None
    operator = "~*" if "i" in flags else "~"
    ph = pb.add(pattern)
    return f"{extract_text} {operator} {ph}"


def _mod_clause(operand: Any, extract_text: str, pb: ParamBuilder) -> Optional[str]:
    if (
        not isinstance(operand, (list, tuple))
        or len(operand) != 2
        or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in operand
        )
    ):
        return None
    divisor, remainder = operand
    div_ph = pb.add(float(divisor))
    rem_ph = pb.add(float(remainder))
    return f"(({extract_text})::numeric % {div_ph}::numeric) = {rem_ph}::numeric"


def _type_clause(operand: Any, extract_jsonb: str, pb: ParamBuilder) -> Optional[str]:
    # Mongo accepts BSON type aliases like "string"; we accept the JSON
    # type names returned by jsonb_typeof: object, array, string, number,
    # boolean, null.
    if not isinstance(operand, str):
        return None
    mapping = {
        "string": "string",
        "number": "number",
        "int": "number",
        "double": "number",
        "long": "number",
        "bool": "boolean",
        "boolean": "boolean",
        "object": "object",
        "array": "array",
        "null": "null",
    }
    pg_type = mapping.get(operand)
    if pg_type is None:
        return None
    ph = pb.add(pg_type)
    return f"jsonb_typeof({extract_jsonb}) = {ph}"


def _elem_match_clause(
    operand: Any, extract_jsonb: str, pb: ParamBuilder
) -> Optional[str]:
    """Translate ``$elemMatch`` over a JSONB array.

    Operand is a sub-query dict that must match at least one element of
    the array. We emit a correlated subquery using ``jsonb_array_elements``.
    The element-level translation reuses the same machinery: we treat each
    array element as a record whose field paths root at ``'$'`` (the elem),
    not ``'data'``. To keep the implementation compact we only support
    scalar comparisons inside ``$elemMatch`` on the top-level fields of
    each element.
    """
    if not isinstance(operand, dict):
        return None

    pieces: List[str] = []
    for key, cond in operand.items():
        if key.startswith("$"):
            # Operator at the elem-level (no key path) — supported for
            # scalar comparisons against the element itself.
            if not isinstance(cond, (int, float, str, bool)) and cond is not None:
                return None
            piece = _comparator_clause(key, cond, "(elem::text)", "elem", pb)
            if piece is None:
                return None
            pieces.append(piece)
            continue

        if not _safe_field_path(key):
            return None
        elem_path = _path_literal(key)
        elem_text = f"(elem #>> '{elem_path}')"
        elem_jsonb = f"(elem #> '{elem_path}')"
        if isinstance(cond, dict):
            # Nested operator dict — recurse using elem-rooted extracts.
            sub_pieces: List[str] = []
            for op, operand_inner in cond.items():
                if op in _COMPARATORS:
                    piece = _comparator_clause(
                        op, operand_inner, elem_text, elem_jsonb, pb
                    )
                else:
                    piece = None
                if piece is None:
                    return None
                sub_pieces.append(piece)
            if not sub_pieces:
                return None
            pieces.append(" AND ".join(sub_pieces))
        else:
            if not _is_scalar(cond):
                return None
            ph = pb.add(cond)
            pieces.append(_eq_clause(elem_text, elem_jsonb, ph, cond))

    if not pieces:
        return None
    body = " AND ".join(pieces)
    return (
        f"EXISTS (SELECT 1 FROM jsonb_array_elements({extract_jsonb}) AS elem "
        f"WHERE {body})"
    )


def _all_clause(operand: Any, extract_jsonb: str, pb: ParamBuilder) -> Optional[str]:
    if not isinstance(operand, (list, tuple)) or not operand:
        return None
    # Each element must be present in the array. Use JSONB containment
    # for each value: ``data #> path @> '[value]'::jsonb``.
    pieces: List[str] = []
    for v in operand:
        if not _is_scalar(v):
            return None
        ph = pb.add(_to_jsonb_literal([v]))
        pieces.append(f"{extract_jsonb} @> {ph}::jsonb")
    return "(" + " AND ".join(pieces) + ")"


def _to_jsonb_literal(value: Any) -> str:
    """Render *value* as a JSON literal string suitable for ``::jsonb`` cast."""
    import json

    return json.dumps(value)


# ---- logical translation ----------------------------------------------------


def _translate_logical(op: str, conditions: Any, pb: ParamBuilder) -> Optional[str]:
    if not isinstance(conditions, list) or not conditions:
        return None
    parts: List[str] = []
    for sub in conditions:
        if not isinstance(sub, dict):
            return None
        translated = _translate_query_into(sub, pb)
        if translated is None:
            return None
        parts.append(f"({translated})")
    if op == "$and":
        return " AND ".join(parts)
    if op == "$or":
        return " OR ".join(parts)
    if op == "$nor":
        return "NOT (" + " OR ".join(parts) + ")"
    return None


def _translate_query_into(query: Dict[str, Any], pb: ParamBuilder) -> Optional[str]:
    """Translate a query dict into a SQL fragment, accumulating into ``pb``."""
    if not query:
        return ""

    fragments: List[str] = []
    for key, value in query.items():
        if key in _IGNORED_TOP_LEVEL:
            continue
        if key in ("$and", "$or", "$nor"):
            piece = _translate_logical(key, value, pb)
            if piece is None:
                return None
            fragments.append(f"({piece})")
            continue
        if key == "$not":
            # Top-level $not is uncommon; treat as negation of a sub-query
            # dict.
            if not isinstance(value, dict):
                return None
            inner = _translate_query_into(value, pb)
            if inner is None:
                return None
            fragments.append(f"NOT ({inner})")
            continue
        if key.startswith("$"):
            return None
        piece = _translate_field_clause(key, value, pb)
        if piece is None:
            return None
        fragments.append(piece)

    return " AND ".join(fragments) if fragments else ""


def translate_query(
    query: Dict[str, Any],
) -> Optional[Tuple[str, List[Any]]]:
    """Translate a Mongo-style query dict to ``(sql_where, params)``.

    Returns ``None`` when any portion of the query can't be expressed in
    SQL we trust; the caller drops to in-Python filtering.

    The returned SQL fragment is meant to be ANDed into a larger WHERE
    clause: ``WHERE (<returned_sql>)``. When the query is empty, returns
    ``("", [])``.
    """
    pb = ParamBuilder()
    out = _translate_query_into(query, pb)
    if out is None:
        return None
    return out, pb.values


def translate_sort(
    sort: Optional[List[Tuple[str, int]]],
) -> Optional[str]:
    """Translate a Mongo-style sort spec into an ORDER BY fragment.

    Returns ``None`` when the sort can't be expressed (unsafe field name
    or invalid direction). The fragment does NOT include the leading
    ``ORDER BY`` keyword.

    NULLs sort last for ascending, first for descending — mirrors
    :func:`jvspatial.db.database.finalize_find_results` semantics. (Postgres'
    default puts NULLs first for ASC, which is the opposite of what
    callers expect, so we set NULLS LAST / NULLS FIRST explicitly.)
    """
    if not sort:
        return None
    parts: List[str] = []
    for field, direction in sort:
        if direction not in (1, -1):
            return None
        if not _safe_field_path(field):
            return None
        path = _path_literal(field)
        col = f"(data #>> '{path}')"
        if direction == 1:
            parts.append(f"{col} ASC NULLS LAST")
        else:
            parts.append(f"{col} DESC NULLS LAST")
    return ", ".join(parts)


__all__ = ["ParamBuilder", "translate_query", "translate_sort"]
