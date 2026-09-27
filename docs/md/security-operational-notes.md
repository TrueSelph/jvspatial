# Security and operational notes

This page complements [environment-configuration.md](environment-configuration.md) with deployment-facing security behavior.

## OAuth signing key custody

Set `JVSPATIAL_OAUTH_KEY_ENCRYPTION_KEY` to a Fernet key from your secret manager before enabling OAuth in production. Generate one with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`. The keystore encrypts new private keys before persistence and rewraps a legacy plaintext key when it is first loaded. Back up the encryption key separately from the database, keep it identical across workers, and restrict both secret and database access. Missing or incorrect keys cause encrypted-key signing to fail closed. A database backup taken before the first rewrap still contains plaintext and must be protected or replaced. This is application-level encryption, not a managed KMS/HSM integration; key rotation requires an explicit re-encryption procedure before retiring the old key.

## Redis cache

- Use a **dedicated Redis instance** (or logical database + ACLs) per application. Do not share the same keyspace with untrusted writers.
- Default **`JVSPATIAL_REDIS_SERIALIZATION=json`** avoids storing pickle blobs, which could be abused for remote code execution if an attacker could inject Redis values read by your app. Use **`pickle`** only when you fully trust Redis and need arbitrary Python objects in cache.
- Pattern invalidation uses **SCAN** (not `KEYS`) so large keyspaces do not block the server.
- **Layered cache** (L1 memory + L2 Redis) writes the same values to Redis as to L1. If those values are not JSON-serializable, set **`JVSPATIAL_REDIS_SERIALIZATION=pickle`** or restrict cached values to JSON-safe types; otherwise L2 `set` may fail silently (see logs) while L1 still holds the object.

## Webhook API keys in URLs

Webhook authentication can read API keys from query parameters or path segments (see webhook configuration). **Prefer header-based API keys in production.** Query and path parameters are more likely to appear in access logs, reverse proxies, browser history, and `Referer` headers.

Webhook idempotency keys are claimed atomically in the shared database before the handler runs. An in-flight retry or reused key with different request content returns 409. If a worker dies after a claim, the outcome may be uncertain; inspect the downstream effect before clearing the pending record. A database write failure returns 503 rather than relying on process-local memory. Claims only guard requests that supply an idempotency header. Keep webhook side effects idempotent at their own boundary when practical.

## JWT blacklist (fail-closed)

If the database or cache path used for token blacklist checks raises an error, validation **fails closed** by default: the token is treated as blacklisted. Failures are logged at **ERROR** with stack traces. `JVSPATIAL_AUTH_BLACKLIST_FAIL_CLOSED=false` restores the previous availability behavior and should be used only with a documented acceptance of revocation risk. Use a shared session store across workers for prompt cross-worker revocation.

## In-memory rate limiting and auth rate helpers

In-process counters (for example `MemoryRateLimitBackend` and in-memory auth attempt tracking) **do not synchronize across workers or hosts**. For multiple uvicorn workers, Kubernetes replicas, or autoscaling groups, use a **shared backend** (for example Redis-backed rate limiting) so limits apply globally.

Auth entry points keep their 5/60s per-IP cap when global rate limiting is off. Set `rate_limit.auth_entrypoint_rate_limit_enabled=False` only in tests or when the host application supplies an equivalent trusted limiter. This is an explicit server configuration choice; disabling the global limiter does not turn it off (`jvspatial/api/server_configurator.py:95`, `jvspatial/api/server_configurator.py:173`).
