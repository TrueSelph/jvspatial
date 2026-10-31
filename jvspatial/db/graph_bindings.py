"""Read-only one-hop graph binding facts, without application access policy."""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class LiteralBindingFact:
    """An exact persisted literal with optional conflict-checked legacy storage.

    Missing and JSON null differ. A present value must belong to allowed_values;
    when both paths exist their JSON values must agree. This is a storage fact,
    never an access decision or a hydrated-model default.
    """

    path: str
    allowed_values: Tuple[str, ...]
    legacy_path: Optional[str] = None
    required: bool = True

    def __post_init__(self) -> None:
        """Reject ambiguous paths and mutable or malformed literal declarations."""
        if not isinstance(self.path, str) or not self.path:
            raise ValueError("A canonical fact path is required")
        for path in (self.path, self.legacy_path):
            if path is not None and (
                not isinstance(path, str)
                or not path
                or any(not part for part in path.split("."))
            ):
                raise ValueError("Fact paths must contain nonempty segments")
        if (
            not isinstance(self.allowed_values, tuple)
            or not self.allowed_values
            or any(
                not isinstance(value, str) or not value for value in self.allowed_values
            )
        ):
            raise ValueError(
                "allowed_values must be a nonempty tuple of nonempty strings"
            )
        if type(self.required) is not bool:
            raise ValueError("required must be a bool")


@dataclass(frozen=True)
class GraphBindingSummary:
    """Current matching records and unique-parent bindings in one store read.

    Only complete results describe the full matching audience. Invalid facts or
    edges remain explicit; callers decide whether to fail closed. No principal,
    tenancy admission, rooted-ancestor proof or permission lease is supplied.
    """

    matched: int
    bound: int
    invalid_facts: int
    invalid_edges: int
    complete: bool

    def __post_init__(self) -> None:
        """Keep count and completeness types literal and cardinalities coherent."""
        values = (self.matched, self.bound, self.invalid_facts, self.invalid_edges)
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("Summary counts must be nonnegative integers")
        if (
            any(value > self.matched for value in values[1:])
            or type(self.complete) is not bool
        ):
            raise ValueError("Invalid graph binding summary cardinality")
