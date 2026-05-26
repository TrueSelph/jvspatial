"""``jvspatial`` command-line interface.

Entry point for operational tooling shipped with the library. Today
hosts the ``migrate`` subcommand for bulk schema-migration application;
expected to grow over time.

Wiring (in ``pyproject.toml``)::

    [project.scripts]
    jvspatial = "jvspatial.cli:main"

Usage::

    jvspatial migrate --collection node --entity User --dry-run
    jvspatial migrate --collection node          # all entities in collection
    jvspatial migrate --collection node --apply  # actually persist changes
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import sys
from typing import Iterable, List, Optional, Type

logger = logging.getLogger("jvspatial.cli")


# ---- helpers ---------------------------------------------------------------


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _import_paths(paths: Iterable[str]) -> None:
    """Import every dotted module path so registrations / classes are loaded.

    The migration registry is keyed on class objects — those classes
    have to be importable for the resolver to see them. Likewise the
    user's ``@migration`` decorators need to have run.
    """
    for path in paths:
        if not path:
            continue
        logger.debug("Importing %s", path)
        importlib.import_module(path)


def _discover_classes(collection: str) -> List[Type]:
    """Return all loaded ``Object`` subclasses whose collection matches.

    Walks ``Object.__subclasses__()`` recursively. The migration command
    only needs the subset that touch ``collection``; we filter using the
    same ``type_code -> collection`` map ``Object.get_collection_name``
    uses.
    """
    from jvspatial.core.entities.object import Object

    collection_map = {"n": "node", "e": "edge", "o": "object", "w": "walker"}
    matches: List[Type] = []
    seen = set()
    stack: List[Type] = list(Object.__subclasses__())
    while stack:
        klass = stack.pop()
        if klass in seen:
            continue
        seen.add(klass)
        try:
            tc = klass.model_fields["type_code"].default  # type: ignore[attr-defined]
        except Exception:
            tc = "o"
        if collection_map.get(tc, "object") == collection:
            matches.append(klass)
        stack.extend(klass.__subclasses__())
    return matches


def _entity_name_to_class(entity: str, classes: Iterable[Type]) -> Optional[Type]:
    for klass in classes:
        try:
            name = klass._entity_name()  # type: ignore[attr-defined]
        except Exception:
            name = klass.__name__
        if name == entity:
            return klass
    return None


# ---- migrate subcommand ----------------------------------------------------


async def _run_migrate(args: argparse.Namespace) -> int:
    """Apply migrations against ``args.collection`` records.

    Returns process exit code (0 on success, >0 on failure).
    """
    from jvspatial.core.migrations import (
        MigrationError,
        apply_migrations,
        needs_migration,
    )
    from jvspatial.db.factory import create_database
    from jvspatial.db.manager import get_database_manager

    # Bring user code into scope so @migration decorators register.
    if args.import_module:
        _import_paths(args.import_module)

    # Resolve the database. Default to the prime DB the manager has;
    # fall back to env-driven create_database().
    try:
        db = get_database_manager().get_prime_database()
    except Exception:
        db = create_database("json")  # final fallback for dev
    logger.info("Using database: %s", type(db).__name__)

    candidates = _discover_classes(args.collection)
    if args.entity:
        wanted = _entity_name_to_class(args.entity, candidates)
        if wanted is None:
            logger.error(
                "No Object subclass with entity name %r mapped to "
                "collection %r. Use --import-module to load the "
                "module that defines it.",
                args.entity,
                args.collection,
            )
            return 2
        class_index = {args.entity: wanted}
    else:
        class_index = {}
        for klass in candidates:
            try:
                name = klass._entity_name()  # type: ignore[attr-defined]
            except Exception:
                name = klass.__name__
            class_index.setdefault(name, klass)

    if not class_index:
        logger.error(
            "No Object subclasses loaded for collection %r. Use "
            "--import-module to load your application code.",
            args.collection,
        )
        return 2

    rows = await db.find(args.collection, {})
    logger.info("Scanning %d record(s) in collection %r", len(rows), args.collection)

    migrated = 0
    skipped = 0
    failed = 0
    unmapped: List[str] = []

    for row in rows:
        entity_name = row.get("entity")
        target = class_index.get(entity_name) if entity_name else None
        if target is None:
            unmapped.append(str(row.get("id", "?")))
            skipped += 1
            continue

        if not needs_migration(row, target):
            skipped += 1
            continue

        try:
            upgraded, changed = apply_migrations(row, target)
        except MigrationError as exc:
            logger.error(
                "Migration failed for %s %s: %s",
                target.__name__,
                row.get("id"),
                exc,
            )
            failed += 1
            continue

        if not changed:
            skipped += 1
            continue

        if args.dry_run:
            logger.info(
                "[dry-run] would migrate %s %s",
                target.__name__,
                row.get("id"),
            )
        else:
            await db.save(args.collection, upgraded)
            logger.info(
                "migrated %s %s",
                target.__name__,
                row.get("id"),
            )
        migrated += 1

    logger.info(
        "summary: migrated=%d skipped=%d failed=%d unmapped=%d " "(%s)",
        migrated,
        skipped,
        failed,
        len(unmapped),
        "dry-run" if args.dry_run else "applied",
    )
    if unmapped:
        logger.warning(
            "%d record(s) had no class mapped — likely an unimported "
            "module. Re-run with --import-module to handle them.",
            len(unmapped),
        )

    return 0 if failed == 0 else 1


# ---- entry point -----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level ``argparse`` parser for the ``jvspatial`` CLI."""
    parser = argparse.ArgumentParser(
        prog="jvspatial", description="jvspatial operational CLI"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable DEBUG logging"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    mig = sub.add_parser(
        "migrate",
        help="Apply schema migrations to existing records",
    )
    mig.add_argument(
        "--collection",
        required=True,
        help='Collection to scan ("node" / "edge" / "object" / "walker").',
    )
    mig.add_argument(
        "--entity",
        help=(
            "Restrict to records of this entity name. Default: every "
            "Object subclass that maps to the collection."
        ),
    )
    mig.add_argument(
        "--import-module",
        action="append",
        default=[],
        help=(
            "Dotted import path to load before running. Repeat for "
            "each module. Use this so the migration registry sees "
            "your app's @migration decorators and class definitions."
        ),
    )
    group = mig.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report what would migrate without writing (default).",
    )
    group.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Actually persist migrated records back to the database.",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point. Parses ``argv`` and dispatches to the chosen command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.cmd == "migrate":
        return asyncio.run(_run_migrate(args))

    parser.error(f"Unknown command: {args.cmd!r}")
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
