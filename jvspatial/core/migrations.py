"""Schema migration framework for ``Object`` subclasses.

Adding / renaming / removing a field on an entity today silently
orphans data: old records still load (Pydantic accepts the extra
fields per ``model_config = ConfigDict(extra="ignore")``), but renamed
fields look unset and removed fields stay forever in the JSONB blob.
ROADMAP §2.1 calls this out as a production hazard.

This module adds a thin, opt-in migration layer:

1. Every ``Object`` gets a ``__schema_version__: ClassVar[int] = 1``
   discriminator. Subclasses bump it when the on-disk shape changes.
2. The persisted record carries the version under the ``_v`` key.
3. Authors register migrations with the :func:`migration` decorator,
   keyed by ``(class, from_version, to_version)``.
4. :func:`apply_migrations` walks the chain from the persisted version
   to the current class version, applying each step in order.
5. Hooks in the ``Object`` / ``Node`` / ``Walker`` load path call
   :func:`apply_migrations` on every fetch (E2). The optional
   ``auto_persist_migrations`` flag re-saves upgraded records.
6. The ``jvspatial migrate`` CLI bulk-applies migrations against a
   collection (E3).

The framework is conservative by default:

* Migrations only run when the persisted ``_v`` is *less than* the
  class version. Newer records than the running code are passed
  through unchanged (and a warning logged) — refusing to silently
  downgrade.
* No auto-persist by default; load-path migration is in-memory only
  until the caller saves the record explicitly.

Closes ROADMAP §2.1.
"""

from __future__ import annotations

import logging
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
)

logger = logging.getLogger(__name__)

# Standard key used in persisted records to store the schema version.
SCHEMA_VERSION_KEY: str = "_v"

# Default version assumed for legacy records that predate the framework.
LEGACY_VERSION: int = 1

T = TypeVar("T")
MigrationFn = Callable[[Dict[str, Any]], Dict[str, Any]]


class MigrationError(Exception):
    """Raised when migration can't proceed (missing step, downgrade, etc.)."""


class _Registry:
    """Per-process registry of migration callables keyed by (class, from, to).

    Singleton — module-level :data:`registry` is the canonical instance.
    Tests use :meth:`snapshot` / :meth:`restore` to isolate.
    """

    def __init__(self) -> None:
        # (cls, from_v, to_v) -> callable
        self._migrations: Dict[Tuple[Type[Any], int, int], MigrationFn] = {}

    def register(
        self,
        cls: Type[Any],
        from_version: int,
        to_version: int,
        fn: MigrationFn,
    ) -> None:
        if from_version >= to_version:
            raise MigrationError(
                f"migration from_version ({from_version}) must be < "
                f"to_version ({to_version})"
            )
        key = (cls, int(from_version), int(to_version))
        if key in self._migrations:
            raise MigrationError(
                f"duplicate migration registered: {cls.__name__} "
                f"{from_version} -> {to_version}"
            )
        self._migrations[key] = fn

    def get_chain(
        self, cls: Type[Any], from_version: int, to_version: int
    ) -> List[MigrationFn]:
        """Resolve the in-order chain of migrations from ``from_version``.

        The resolver walks the MRO so a migration registered on a
        parent class applies to subclasses too, unless the subclass
        registers its own migration for the same version pair.

        Args:
            cls: The Object subclass whose record is being migrated.
            from_version: Version stamped on the persisted record.
            to_version: Target version (typically ``cls.__schema_version__``).

        Returns:
            List of callables to invoke in order.

        Raises:
            MigrationError: No path from ``from_version`` to
                ``to_version`` is registered.
        """
        if from_version == to_version:
            return []
        if from_version > to_version:
            raise MigrationError(
                f"refusing to downgrade {cls.__name__}: persisted "
                f"version {from_version} > class version {to_version}"
            )

        chain: List[MigrationFn] = []
        cursor = from_version
        while cursor < to_version:
            step = self._resolve_step(cls, cursor)
            if step is None:
                raise MigrationError(
                    f"no migration registered for {cls.__name__} "
                    f"version {cursor} -> {cursor + 1} (target {to_version})"
                )
            next_version, fn = step
            chain.append(fn)
            cursor = next_version
        return chain

    def _resolve_step(
        self, cls: Type[Any], from_version: int
    ) -> Optional[Tuple[int, MigrationFn]]:
        """Find the migration starting at ``from_version`` for ``cls``.

        Searches subclass-then-parent so subclasses can override an
        inherited migration. Among multiple registrations starting at
        the same version, picks the one with the **smallest**
        ``to_version`` — we always step one canonical version at a
        time. Authors who want to skip versions register the
        intermediate steps; the chain walks them.
        """
        candidates: List[Tuple[int, MigrationFn]] = []
        for klass in cls.__mro__:
            for (registered_cls, fv, tv), fn in self._migrations.items():
                if registered_cls is klass and fv == from_version:
                    candidates.append((tv, fn))
            # If a class has any registration, stop searching parents
            # — subclass wins.
            if candidates:
                break
        if not candidates:
            return None
        candidates.sort(key=lambda pair: pair[0])
        return candidates[0]

    def snapshot(self) -> Dict[Tuple[Type[Any], int, int], MigrationFn]:
        return dict(self._migrations)

    def restore(self, snap: Dict[Tuple[Type[Any], int, int], MigrationFn]) -> None:
        self._migrations = dict(snap)

    def clear(self) -> None:
        self._migrations.clear()


# Canonical module-level registry.
registry = _Registry()


def migration(
    cls: Type[Any],
    *,
    from_version: int,
    to_version: int,
) -> Callable[[MigrationFn], MigrationFn]:
    """Decorator: register ``fn`` as a migration step for ``cls``.

    The decorated callable receives the persisted record dict and
    returns the upgraded dict. The callable may mutate the input dict
    in place and return it, or return a new dict — both are fine.

    Args:
        cls: The ``Object`` subclass this migration applies to. Use
            the most specific class; the resolver walks the MRO so
            registrations on a parent class apply to children that
            don't override.
        from_version: Persisted version this migration reads.
        to_version: Version produced by this migration. Conventionally
            ``from_version + 1`` — skipping versions makes the chain
            harder to reason about.

    Example::

        @migration(User, from_version=1, to_version=2)
        def add_email_field(record):
            record["email"] = record.pop("email_address", None)
            return record

    Returns:
        The original callable (registration is the side effect).

    Raises:
        MigrationError: ``from_version >= to_version`` or a duplicate
            ``(cls, from, to)`` triple was registered.
    """

    def _decorator(fn: MigrationFn) -> MigrationFn:
        registry.register(cls, from_version, to_version, fn)
        return fn

    return _decorator


def _resolve_target_version(cls: Type[Any]) -> int:
    """Read ``__schema_version__`` from ``cls`` or fall back to LEGACY."""
    return int(getattr(cls, "__schema_version__", LEGACY_VERSION))


def needs_migration(record: Dict[str, Any], cls: Type[Any]) -> bool:
    """Return True iff ``record`` is below the current class schema version."""
    record_v = int(record.get(SCHEMA_VERSION_KEY, LEGACY_VERSION))
    target = _resolve_target_version(cls)
    return record_v < target


def apply_migrations(
    record: Dict[str, Any], cls: Type[Any]
) -> Tuple[Dict[str, Any], bool]:
    """Migrate ``record`` up to the current class version, if needed.

    The function is deliberately tolerant of the legacy zero-state:
    records without a ``_v`` key are treated as version ``LEGACY_VERSION``
    (currently ``1``). New code that bumps to version 2 only needs to
    register a single ``from_version=1, to_version=2`` migration.

    Args:
        record: Persisted record dict (from `Database.find` / `get`).
        cls: The ``Object`` subclass the record should hydrate as.

    Returns:
        ``(upgraded_record, was_migrated)`` — when no migration was
        needed, returns the original record + ``False``. When at least
        one step ran, returns the new dict + ``True``. The returned
        dict always has ``_v`` set to the target version so callers
        that persist it back leave the record cleanly stamped.

    Raises:
        MigrationError: persisted version exceeds class version
            (downgrade refused) or chain is incomplete.
    """
    record_v = int(record.get(SCHEMA_VERSION_KEY, LEGACY_VERSION))
    target = _resolve_target_version(cls)
    if record_v == target:
        return record, False
    if record_v > target:
        raise MigrationError(
            f"refusing to downgrade {cls.__name__} record "
            f"{record.get('id')!r}: persisted version {record_v} > "
            f"class version {target}"
        )

    chain = registry.get_chain(cls, record_v, target)
    out = record
    for step in chain:
        out = step(out)
    if not isinstance(out, dict):
        raise MigrationError(
            f"migration step for {cls.__name__} returned "
            f"{type(out).__name__}, expected dict"
        )
    out[SCHEMA_VERSION_KEY] = target
    return out, True


__all__ = [
    "SCHEMA_VERSION_KEY",
    "LEGACY_VERSION",
    "MigrationError",
    "migration",
    "registry",
    "apply_migrations",
    "needs_migration",
]
