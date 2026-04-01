# Security and operational notes

This page complements [environment-configuration.md](environment-configuration.md) with deployment-facing security behavior.

## Redis cache

- Use a **dedicated Redis instance** (or logical database + ACLs) per application. Do not share the same keyspace with untrusted writers.
- Default **`JVSPATIAL_REDIS_SERIALIZATION=json`** avoids storing pickle blobs, which could be abused for remote code execution if an attacker could inject Redis values read by your app. Use **`pickle`** only when you fully trust Redis and need arbitrary Python objects in cache.
- Pattern invalidation uses **SCAN** (not `KEYS`) so large keyspaces do not block the server.
- **Layered cache** (L1 memory + L2 Redis) writes the same values to Redis as to L1. If those values are not JSON-serializable, set **`JVSPATIAL_REDIS_SERIALIZATION=pickle`** or restrict cached values to JSON-safe types; otherwise L2 `set` may fail silently (see logs) while L1 still holds the object.

## Webhook API keys in URLs

Webhook authentication can read API keys from query parameters or path segments (see webhook configuration). **Prefer header-based API keys in production.** Query and path parameters are more likely to appear in access logs, reverse proxies, browser history, and `Referer` headers.

## JWT blacklist (fail-open)

If the database or cache path used for token blacklist checks raises an error, validation **fails open**: the token is treated as **not** blacklisted so the API stays available. Failures are logged at **ERROR** with stack traces—monitor these logs in production because revocation may be ineffective until the underlying issue is fixed.

## In-memory rate limiting and auth rate helpers

In-process counters (for example `MemoryRateLimitBackend` and in-memory auth attempt tracking) **do not synchronize across workers or hosts**. For multiple uvicorn workers, Kubernetes replicas, or autoscaling groups, use a **shared backend** (for example Redis-backed rate limiting) so limits apply globally.
