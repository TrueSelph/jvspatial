"""Pluggable session-state store for the auth subsystem.

Encapsulates the small TTL'd key/value caches that AuthenticationService
and APIKeyService used to hold in process-local dicts. When jvspatial is
deployed across multiple workers (Gunicorn, multi-Lambda), those local
dicts diverge — a token revoked in worker A still validates in worker B
until the per-worker TTL elapses, and rate-limit counters undercount the
true rate by the worker count.

This module wraps both behaviors behind a tiny shared interface and ships
two backends:

* :class:`InProcessSessionStore` — wraps a regular ``dict`` (and is the
  default, preserving the legacy single-worker behavior).
* :class:`RedisSessionStore` — wraps a :class:`jvspatial.cache.redis.RedisCache`
  for cross-worker shared state. Opt-in via constructor or via
  ``Server(auth={"session_store": "redis://..."})``.

The contract is intentionally narrow: ``get`` / ``set`` / ``delete`` with
optional per-call TTL. This isn't a general-purpose cache layer; it's the
glue that lets AuthService stop owning its own state and start using
external storage when a deployment needs it.

Closes ROADMAP §2.3.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


class SessionStore(Protocol):
    """Minimal shared-state interface used by the auth subsystem."""

    async def get(self, key: str) -> Optional[Any]:
        """Return the cached value for ``key`` or ``None`` when absent/expired."""
        ...

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store ``value`` under ``key``. ``ttl`` is seconds; ``None`` = no expiry."""
        ...

    async def delete(self, key: str) -> None:
        """Remove ``key`` if present."""
        ...


class InProcessSessionStore:
    """Backwards-compatible in-process store backed by a ``dict``.

    Honors a per-entry TTL stored alongside the value; ``get`` returns
    ``None`` when the TTL has elapsed and prunes the stale entry. This is
    the default — preserves the legacy single-worker behavior with zero
    operational surface.

    Not concurrency-safe across asyncio tasks (no lock); jvspatial's auth
    paths already serialize blacklist writes around the DB lookup so
    this is fine. Don't share an instance across threads.
    """

    def __init__(self, default_ttl: int = 300) -> None:
        self._default_ttl = max(0, int(default_ttl))
        # value, expires_at_unix (None = no expiry)
        self._data: dict[str, tuple[Any, Optional[float]]] = {}

    async def get(self, key: str) -> Optional[Any]:
        """Return value for ``key`` or ``None`` when absent/expired."""
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.time() >= expires_at:
            self._data.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store ``value`` under ``key`` with optional TTL (seconds)."""
        effective_ttl = self._default_ttl if ttl is None else int(ttl)
        expires_at = time.time() + effective_ttl if effective_ttl > 0 else None
        self._data[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        """Remove ``key`` if present."""
        self._data.pop(key, None)


class RedisSessionStore:
    """Redis-backed shared store using the jvspatial cache layer.

    Constructed via :func:`create_session_store`; do not instantiate
    directly unless you've already wired a :class:`RedisCache`.

    Args:
        cache: A :class:`jvspatial.cache.redis.RedisCache` instance. Owns
            the connection lifecycle — this wrapper just delegates the
            get/set/delete calls.
        default_ttl: TTL in seconds applied when ``set`` is called without
            an explicit ttl. Default 300s — matches the AuthService
            blacklist cache window.
        prefix: Namespace prefix prepended to every key. Default
            ``"jvs:session:"`` keeps these entries out of the way of other
            cache users on the same Redis.
    """

    def __init__(
        self,
        cache: Any,
        *,
        default_ttl: int = 300,
        prefix: str = "jvs:session:",
    ) -> None:
        self._cache = cache
        self._default_ttl = max(0, int(default_ttl))
        self._prefix = str(prefix)

    def _k(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Return value for ``key`` from Redis or ``None`` on miss/error."""
        try:
            raw = await self._cache.get(self._k(key))
        except Exception as exc:  # pragma: no cover - depends on live Redis
            logger.warning(
                "RedisSessionStore.get(%s) failed (%s); treating as miss",
                key,
                exc,
            )
            return None
        if raw is None:
            return None
        # The RedisCache layer already JSON-encodes values on set; on
        # the way out it may give us the raw string or the decoded
        # object depending on configuration. Handle both.
        if isinstance(raw, (bytes, bytearray)):
            try:
                return json.loads(bytes(raw).decode("utf-8"))
            except Exception:
                return None
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return raw
        return raw

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store ``value`` in Redis under ``key`` with optional TTL."""
        effective_ttl = self._default_ttl if ttl is None else int(ttl)
        try:
            await self._cache.set(
                self._k(key),
                json.dumps(value, default=str),
                ttl=effective_ttl if effective_ttl > 0 else None,
            )
        except Exception as exc:  # pragma: no cover - depends on live Redis
            logger.warning(
                "RedisSessionStore.set(%s) failed (%s); state will diverge",
                key,
                exc,
            )

    async def delete(self, key: str) -> None:
        """Remove ``key`` from Redis if present."""
        try:
            await self._cache.delete(self._k(key))
        except Exception as exc:  # pragma: no cover
            logger.warning("RedisSessionStore.delete(%s) failed (%s)", key, exc)


def create_session_store(
    backend: Optional[Any] = None,
    *,
    default_ttl: int = 300,
    prefix: str = "jvs:session:",
) -> SessionStore:
    """Build the right session store from a config hint.

    Args:
        backend: One of:

            * ``None`` — return :class:`InProcessSessionStore` (the
              default; matches legacy behavior).
            * ``"memory"`` — same as ``None``.
            * ``"redis"`` — instantiate a :class:`RedisCache` from env
              (``JVSPATIAL_REDIS_URL``) and wrap it.
            * a Redis URL like ``"redis://localhost:6379/0"`` — same as
              ``"redis"`` but with an explicit URL.
            * an already-constructed :class:`CacheBackend` instance — wrap
              it directly. Lets advanced callers reuse a cache pool they
              already manage.

        default_ttl: TTL applied when ``set`` is called without an
            explicit ttl. Default 300s.
        prefix: Namespace prefix for Redis keys. Ignored for the
            in-process backend.

    Returns:
        A :class:`SessionStore` implementation.
    """
    if backend is None or backend == "memory":
        return InProcessSessionStore(default_ttl=default_ttl)

    if isinstance(backend, str) and backend == "redis":
        from jvspatial.cache.factory import create_cache
        from jvspatial.env import env

        redis_url = env("JVSPATIAL_REDIS_URL")
        if not redis_url:
            raise ValueError(
                "create_session_store(backend='redis') requires JVSPATIAL_REDIS_URL"
            )
        cache = create_cache("redis", redis_url=redis_url, prefix=prefix)
        return RedisSessionStore(cache, default_ttl=default_ttl, prefix=prefix)

    if isinstance(backend, str) and backend.startswith(("redis://", "rediss://")):
        from jvspatial.cache.factory import create_cache

        cache = create_cache("redis", redis_url=backend, prefix=prefix)
        return RedisSessionStore(cache, default_ttl=default_ttl, prefix=prefix)

    # Anything else: assume it's already a CacheBackend-compatible object.
    return RedisSessionStore(backend, default_ttl=default_ttl, prefix=prefix)


__all__ = [
    "SessionStore",
    "InProcessSessionStore",
    "RedisSessionStore",
    "create_session_store",
]
