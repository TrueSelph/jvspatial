"""``@deprecated`` decorator + sibling of :mod:`jvspatial.utils.stability`.

Marks an API as scheduled for removal. Each call emits a
:class:`DeprecationWarning` with the replacement and the planned
removal version. As with the :mod:`stability` decorator, the warning
fires only once per fully-qualified name per process to avoid log
spam, and is suppressed under serverless mode where cold starts
make once-per-process semantics meaningless.

Usage::

    from jvspatial.utils.deprecation import deprecated

    @deprecated(
        replacement="Database.find_many()",
        remove_in="0.X+1",
        note="See docs/md/stability.md#deprecation-policy",
    )
    async def old_bulk_get(...):
        ...

The replacement text appears in the warning message; ``remove_in``
gives adopters a deadline.
"""

from __future__ import annotations

import asyncio
import functools
import threading
import warnings
from typing import Any, Callable, Optional, Set, TypeVar, cast

from jvspatial.runtime.serverless import is_serverless_mode

F = TypeVar("F", bound=Callable[..., Any])


_warned_names: Set[str] = set()
_warned_lock = threading.Lock()


def _emit_once(name: str, message: str) -> None:
    """Emit a :class:`DeprecationWarning` at most once per ``name``."""
    if is_serverless_mode():
        return
    with _warned_lock:
        if name in _warned_names:
            return
        _warned_names.add(name)
    warnings.warn(
        f"jvspatial: {name} is deprecated. {message}",
        DeprecationWarning,
        stacklevel=3,
    )


def deprecated(
    *,
    replacement: Optional[str] = None,
    remove_in: Optional[str] = None,
    note: str = "",
    name: Optional[str] = None,
) -> Callable[[F], F]:
    """Decorator marking a callable as deprecated.

    Args:
        replacement: Recommended substitute (string description).
        remove_in: Version in which the deprecated symbol is planned
            to be removed. Helpful for adopters scheduling migrations.
        note: Optional additional context (link to issue, migration
            guide).
        name: Optional explicit identifier used in the warning. Defaults
            to ``f"{func.__module__}.{func.__qualname__}"``.

    Returns:
        Decorated callable. Async functions remain async.
    """

    def decorator(func: F) -> F:
        api_name = name or f"{func.__module__}.{func.__qualname__}"

        parts = []
        if replacement:
            parts.append(f"Use {replacement} instead.")
        if remove_in:
            parts.append(f"Scheduled for removal in {remove_in}.")
        if note:
            parts.append(note)
        message = " ".join(parts) if parts else "Will be removed."

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                _emit_once(api_name, message)
                return await func(*args, **kwargs)

            return cast(F, async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            _emit_once(api_name, message)
            return func(*args, **kwargs)

        return cast(F, sync_wrapper)

    return decorator


def reset_deprecation_warnings() -> None:
    """Clear the once-per-process suppression set (for tests)."""
    with _warned_lock:
        _warned_names.clear()


__all__ = ["deprecated", "reset_deprecation_warnings"]
