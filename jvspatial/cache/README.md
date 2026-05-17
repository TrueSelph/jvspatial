# jvspatial/cache

Cache backends: memory, Redis, layered. Plus a factory and the abstract base.

> **Read first**: [SPEC §13](../../SPEC.md), [docs/md/caching.md](../../docs/md/caching.md)

---

## Purpose

`cache/` provides pluggable cache backends. The most common use is the read-through DB wrapper enabled via `create_database(cache_get_size=N)` — this package exposes the underlying backends and a factory so callers can build their own cache strategies.

## Layout

```
cache/
├── base.py        # CacheBackend ABC
├── factory.py     # create_cache, create_default_cache
├── memory.py      # MemoryCache (LRU)
├── redis.py       # RedisCache (optional)
└── layered.py     # LayeredCache (memory L1 + redis L2)
```

## Public API (from `jvspatial.cache`)

| Name | What it does |
|---|---|
| `CacheBackend` | ABC for cache backends |
| `create_cache(backend, **kwargs)` | Factory entry point |
| `create_default_cache()` | Env-driven default |
| `MemoryCache` | Per-process LRU |
| `RedisCache` | Shared cross-process cache (requires `redis-py`) |
| `LayeredCache` | Memory L1 + Redis L2, promotes hot keys to L1 |

## Invariants

- **Memory cache is per-process.** Cross-worker invalidation requires Redis or layered backend.
- **TTL is per-cache-instance, default `None`.** Cache until eviction.
- **DB-wrapped caches invalidate on `save` / `delete`.** No stale read after a write through the wrapped database. (`jvspatial/db/_cache.py`, internal)
- **`bulk_save` and `find_one_and_update` refresh the cache** for affected keys; other writes invalidate.
- **Cache is skipped in serverless mode** when wrapped via `create_database(cache_get_size=N)`. Cold-start memory does not survive invocations anyway.

## Modification patterns

- **Adding a backend**: implement `CacheBackend`. Register in `create_cache` factory. Decide eviction semantics up front.
- **Changing invalidation rules**: edit `jvspatial/db/_cache.py` (internal). Add tests that cover save / delete / bulk_save / find_one_and_update.
- **Tuning the read-through wrapper**: pass `cache_get_size=`, `cache_get_ttl=` to `create_database`. Do not import `CachingDatabase` directly.

## Related docs

- [docs/md/caching.md](../../docs/md/caching.md)
- [docs/md/optimization.md](../../docs/md/optimization.md)

## Stability

`CacheBackend`, `create_cache`, `MemoryCache` are stable. `RedisCache` and `LayeredCache` are stable when their optional dependency is installed. Internal wrappers (`jvspatial/db/_cache.py`) are not part of the public surface.
