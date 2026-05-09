"""Async retry with exponential backoff and full jitter.

A small, dependency-free retry primitive that the database adapters
(Mongo connection-failure recovery, DynamoDB throttling, S3
throttling) and any application code can share.

Design choices
--------------
* **Exponential + full jitter.** ``delay = random_uniform(0, base * 2**n)``
  for attempt ``n``, capped at ``max_delay``. Full jitter (rather than
  equal jitter or no jitter) gives the best behavior under thundering-
  herd retries, per AWS Architecture Blog's analysis -- it spreads
  retries uniformly over each window rather than clustering them.
* **Configurable retryable predicate.** Callers pass either a tuple of
  exception types or an explicit ``Callable[[BaseException], bool]``.
  Non-retryable exceptions raise immediately. Anything not classified
  as retryable propagates through.
* **Async-only.** The DB adapters are all ``async``. A sync version
  could be added later if needed; we deliberately don't ship one
  today.
* **No background timers.** Sleep is ``asyncio.sleep`` between
  attempts. Compatible with Lambda / serverless -- the wait is part
  of the request lifetime.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import random
from typing import Any, Awaitable, Callable, Tuple, Type, TypeVar, Union

logger = logging.getLogger(__name__)

T = TypeVar("T")
RetryablePredicate = Callable[[BaseException], bool]
RetrySpec = Union[
    Type[BaseException], Tuple[Type[BaseException], ...], RetryablePredicate
]


def _make_predicate(spec: RetrySpec) -> RetryablePredicate:
    """Normalize ``spec`` into a callable returning bool."""
    if isinstance(spec, type) and issubclass(spec, BaseException):
        types: Tuple[Type[BaseException], ...] = (spec,)

        def _is_one_of(exc: BaseException) -> bool:
            return isinstance(exc, types)

        return _is_one_of
    if isinstance(spec, tuple) and all(
        isinstance(t, type) and issubclass(t, BaseException) for t in spec
    ):
        types_tuple: Tuple[Type[BaseException], ...] = spec

        def _is_in_tuple(exc: BaseException) -> bool:
            return isinstance(exc, types_tuple)

        return _is_in_tuple
    if callable(spec):
        return spec
    raise TypeError(
        "retry_on must be an Exception subclass, a tuple of them, or a "
        "callable predicate"
    )


def _compute_backoff(
    attempt: int, base_delay: float, max_delay: float, jitter: bool
) -> float:
    """Return the delay (in seconds) before retry attempt ``attempt`` (0-indexed).

    Exponential backoff: ``base_delay * 2**attempt`` capped at ``max_delay``.
    With jitter, the actual sleep is uniform over ``[0, capped]``.
    """
    capped = min(max_delay, base_delay * (2**attempt))
    if not jitter:
        return capped
    return random.uniform(0, capped)


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    retry_on: RetrySpec,
    max_attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 5.0,
    jitter: bool = True,
    on_retry: Callable[[BaseException, int, float], None] | None = None,
    **kwargs: Any,
) -> T:
    """Call ``func(*args, **kwargs)`` with retry on transient failures.

    Args:
        func: The async callable to invoke.
        retry_on: Which exceptions to retry. Either an exception type,
            a tuple of types, or a predicate ``(exc) -> bool``.
        max_attempts: Total attempts including the first try. Default 3.
            Must be >= 1.
        base_delay: Initial backoff in seconds. Subsequent attempts
            double this (capped at ``max_delay``).
        max_delay: Upper bound on a single sleep duration.
        jitter: Whether to apply full jitter to each sleep.
        on_retry: Optional hook ``(exc, attempt_number, sleep_seconds) -> None``
            invoked just before each retry sleep. Useful for logging or
            metric emission. The hook must not raise.

    Returns:
        ``func``'s return value on success.

    Raises:
        The last exception ``func`` raised, after exhausting attempts
        OR a non-retryable exception immediately.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    predicate = _make_predicate(retry_on)
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)
        except BaseException as exc:
            last_exc = exc
            if not predicate(exc):
                raise
            if attempt + 1 >= max_attempts:
                # Final attempt failed; propagate.
                raise
            sleep_for = _compute_backoff(attempt, base_delay, max_delay, jitter)
            if on_retry is not None:
                # Hook must not raise; defensive suppression.
                with contextlib.suppress(Exception):  # pragma: no cover
                    on_retry(exc, attempt + 1, sleep_for)
            else:
                logger.debug(
                    "retry_async: attempt %d/%d failed (%s); sleeping %.3fs",
                    attempt + 1,
                    max_attempts,
                    exc,
                    sleep_for,
                )
            await asyncio.sleep(sleep_for)
    # Unreachable -- the loop either returns or raises.
    assert last_exc is not None
    raise last_exc


def retry(
    *,
    retry_on: RetrySpec,
    max_attempts: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 5.0,
    jitter: bool = True,
    on_retry: Callable[[BaseException, int, float], None] | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator form of :func:`retry_async`.

    Example::

        from pymongo.errors import ConnectionFailure
        from jvspatial.utils.retry import retry

        @retry(retry_on=ConnectionFailure, max_attempts=4, base_delay=0.05)
        async def fetch():
            ...
    """

    def decorator(
        func: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await retry_async(
                func,
                *args,
                retry_on=retry_on,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter=jitter,
                on_retry=on_retry,
                **kwargs,
            )

        return wrapper

    return decorator


__all__ = ["retry", "retry_async"]
