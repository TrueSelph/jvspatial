"""Portable index descriptions with a deterministic PostgreSQL DDL boundary.

Descriptions are trusted schema inputs, never query- or tenant-supplied SQL.
Hosts own catalog approval and migrations; database adapters own compilation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field

from jvspatial.exceptions import DatabaseError


class ManagedSchemaError(DatabaseError):
    """A verify-only adapter needs an operator-provisioned schema object."""


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]{0,62}", value
    ):
        raise ValueError("Invalid storage identifier")
    return '"' + value + '"'


def _canonical_tokens(expression: str, *, ordering=False):
    tokens = re.findall(
        r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|#>>|#>|->>|->|::|>=|<=|<>|!=|[^\s]",
        expression,
    )
    tokens = [t if t.startswith(("'", '"')) else t.lower() for t in tokens]
    if ordering:
        if tokens[-3:] == ["asc", "nulls", "last"]:
            tokens = tokens[:-3]
        elif tokens[-1:] == ["asc"]:
            tokens = tokens[:-1]
        elif tokens[-1:] == ["desc"]:
            tokens += ["nulls", "first"]
    return tokens


@dataclass(frozen=True)
class IndexSpec:
    """A physical index, independent of installations and request execution.

    ``keys`` and ``predicate`` are adapter/compiler-produced expressions. Apps
    must use a host's typed proposal interface, not construct these expressions.
    Ownership and query references do not change physical equivalence.
    """

    logical_id: str
    owner: str
    table: str
    keys: tuple[str, ...]
    schema: str = "public"
    method: str = "btree"
    predicate: str = ""
    unique: bool = False
    required: bool = False
    version: str = "1"
    queries: tuple[str, ...] = field(default_factory=tuple)
    justification: str = ""

    def __post_init__(self):
        identifier(self.schema)
        identifier(self.table)
        if self.method not in {
            "btree",
            "gin",
            "gist",
            "hash",
            "brin",
            "hnsw",
            "ivfflat",
        }:
            raise ValueError("Invalid index method")
        if not self.keys or (self.unique and self.method != "btree"):
            raise ValueError("Invalid index keys or uniqueness")
        for expression in (*self.keys, self.predicate):
            if not isinstance(expression, str) or any(
                t in expression for t in (";", "--", "/*", "\x00")
            ):
                raise ValueError("Unsafe schema expression")
        if not self.logical_id or not self.owner:
            raise ValueError("Index identity and owner are required")

    @property
    def fingerprint(self) -> str:
        physical = {
            k: getattr(self, k)
            for k in ("schema", "table", "method", "keys", "predicate", "unique")
        }
        physical["keys"] = [
            _canonical_tokens(k, ordering=self.method == "btree") for k in self.keys
        ]
        physical["predicate"] = _canonical_tokens(self.predicate)
        return hashlib.sha256(
            json.dumps(physical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @property
    def name(self) -> str:
        return f"ix_{self.table[:20]}_{self.fingerprint[:24]}"

    def create_sql(self, *, concurrently: bool = True) -> str:
        return (
            f"CREATE {'UNIQUE ' if self.unique else ''}INDEX "
            f"{'CONCURRENTLY ' if concurrently else ''}{identifier(self.name)} ON "
            f"{identifier(self.schema)}.{identifier(self.table)} USING {self.method} "
            f"({', '.join(self.keys)})"
            + (f" WHERE {self.predicate}" if self.predicate else "")
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "IndexSpec":
        payload = dict(value)
        payload["keys"] = tuple(payload["keys"])
        payload["queries"] = tuple(payload.get("queries", ()))
        return cls(**payload)


def definition_digest(definition: str) -> str:
    """Fingerprint PostgreSQL's own normalized catalog definition."""
    return hashlib.sha256(definition.encode()).hexdigest()
