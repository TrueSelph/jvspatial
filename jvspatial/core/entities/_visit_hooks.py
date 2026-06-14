"""Shared visit-hook registration for Node and Edge subclasses.

Both ``Node`` and ``Edge`` accept ``@on_visit`` decorated methods that
register against one or more ``Walker`` target types. The discovery and
validation logic is identical for the two — this module hosts the shared
implementation so the two ``__init_subclass__`` hooks don't duplicate
~50 lines apiece.

Internal module (underscore-prefixed): callers outside ``jvspatial.core.entities``
should not import from here.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Type

from jvspatial.exceptions import ValidationError


def register_visit_hooks(cls: Type[Any], *, label: str) -> Dict[Any, List[Any]]:
    """Collect ``@on_visit`` decorated methods on ``cls`` and group by target.

    Walks ``cls``'s functions, looks at the ``_is_visit_hook`` / ``_visit_targets``
    metadata set by the ``@on_visit`` decorator, and returns a dict keyed by
    target (a ``Walker`` subclass, a string forward reference, or ``None``
    for "any walker").

    Args:
        cls: The Node or Edge subclass being initialized.
        label: Either ``"Node"`` or ``"Edge"`` — used in error messages so
            users see the right context when their target type is wrong.

    Returns:
        Mapping from target key to list of bound hook methods. Empty dict
        when no ``@on_visit`` methods are present.

    Raises:
        ValidationError: When a target is not a string, not a class, or
            is a class that isn't a ``Walker`` subclass.
    """
    # Import here to avoid a circular import at module-load time:
    # walker.py imports from node.py, node.py imports this module.
    from .walker import Walker

    hooks: Dict[Any, List[Any]] = {}

    for _name, method in inspect.getmembers(cls, inspect.isfunction):
        if not hasattr(method, "_is_visit_hook"):
            continue

        targets = getattr(method, "_visit_targets", None)

        if targets is None:
            # No targets specified — register for any Walker.
            hooks.setdefault(None, []).append(method)
            continue

        for target in targets:
            if isinstance(target, str):
                # Forward reference — resolved at runtime when the walker visits.
                hooks.setdefault(target, []).append(method)
                continue

            if inspect.isclass(target) and issubclass(target, Walker):
                hooks.setdefault(target, []).append(method)
                continue

            target_name = getattr(target, "__name__", target)
            raise ValidationError(
                f"{label} @on_visit must target Walker types "
                f"(or string names), got {target_name}",
                details={
                    "target_type": str(target),
                    "expected_type": "Walker or string",
                },
            )

    return hooks


__all__ = ["register_visit_hooks"]
