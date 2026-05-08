"""API stability markers.

Provides the :func:`experimental` decorator and the
:exc:`ExperimentalWarning` warning class. See
``docs/md/stability.md`` for the contract these enforce.

Why this exists
---------------
Some library APIs are useful enough to ship but not stable enough to
promise compatibility for. The conventional Python pattern is to mark
them with a runtime warning so callers see, exactly once, that they're
opting into something that may change.

Design notes
------------
* The first call to a decorated function emits an
  :exc:`ExperimentalWarning`. Subsequent calls in the same process are
  silent. This avoids log spam without requiring the caller to manage
  ``warnings.filterwarnings`` themselves.
* Warning suppression respects standard ``warnings`` filters, so power
  users can opt out globally
  (``warnings.simplefilter("ignore", ExperimentalWarning)``) or per-name
  using the ``module`` filter.
* Warnings are skipped automatically under serverless mode (where each
  invocation is a fresh process and the "first time" semantics would
  emit on every cold start).
* Both sync and async callables are supported.

Example
-------
::

    from jvspatial.utils.stability import experimental

    @experimental(
        "JsonDB.bulk_insert",
        "may move to JsonDB.save_many() in 0.X+1; see issue #...",
    )
    async def bulk_insert(self, collection, records):
        ...
"""

from __future__ import annotations

import asyncio
import functools
import threading
import warnings
from typing import Any, Callable, Optional, Set, TypeVar, cast

from jvspatial.runtime.serverless import is_serverless_mode

F = TypeVar("F", bound=Callable[..., Any])


class ExperimentalWarning(FutureWarning):
    """Raised once per process the first time an experimental API is called.

    Inherits from :class:`FutureWarning` (rather than
    :class:`DeprecationWarning`) so it shows by default in user code:
    Python suppresses ``DeprecationWarning`` outside of test runners,
    but ``FutureWarning`` is always visible. Adopters of an experimental
    API benefit from seeing the signal during normal development.
    """


# Set of qualified API names we've already warned about in this process.
# Guarded by a threading.Lock so concurrent first-callers can't both
# emit the warning.
_warned_names: Set[str] = set()
_warned_lock = threading.Lock()


def _emit_once(name: str, message: str) -> None:
    """Emit an :class:`ExperimentalWarning` at most once per ``name``."""
    if is_serverless_mode():
        # Cold-start every invocation -- emitting would spam logs without
        # informing anyone who isn't already reading the docs.
        return
    with _warned_lock:
        if name in _warned_names:
            return
        _warned_names.add(name)
    warnings.warn(
        f"jvspatial: {name} is experimental and may change in any "
        f"minor release. {message}",
        ExperimentalWarning,
        stacklevel=3,
    )


def experimental(
    name: Optional[str] = None,
    note: str = "",
) -> Callable[[F], F]:
    """Decorator marking a callable as experimental.

    Args:
        name: Optional explicit name to identify the API in the warning
            message and the once-per-process suppression set. Defaults
            to ``f"{func.__module__}.{func.__qualname__}"``.
        note: Optional additional context (link to issue, expected
            replacement) appended to the warning message.

    Returns:
        Decorated callable. Async functions remain async.
    """

    def decorator(func: F) -> F:
        api_name = name or f"{func.__module__}.{func.__qualname__}"

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                _emit_once(api_name, note)
                return await func(*args, **kwargs)

            return cast(F, async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            _emit_once(api_name, note)
            return func(*args, **kwargs)

        return cast(F, sync_wrapper)

    return decorator


def reset_experimental_warnings() -> None:
    """Clear the once-per-process suppression set.

    Primarily useful for tests that want to re-trigger the warning
    behavior across multiple cases.
    """
    with _warned_lock:
        _warned_names.clear()


__all__ = [
    "ExperimentalWarning",
    "experimental",
    "reset_experimental_warnings",
]
