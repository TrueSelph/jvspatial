# jvspatial — Foundation Audit

> **Purpose**: First retrospective audit of the jvspatial foundation against the contracts now codified in [SPEC.md](SPEC.md), [PRD.md](PRD.md), and [CLAUDE.md](CLAUDE.md). Findings are the backlog for the next phase of hardening.
>
> **Method**: Five parallel reviewers, one per dimension: async contract, security boundaries, database adapter parity, walker/identity invariants, serverless/config/stability. Each returned a severity-tagged finding table with file:line citations.
>
> **Date**: 2026-05-17.
> **Library version**: 0.0.8.
> **Tests collected at audit time**: 1845.

---

## Executive Summary

**150 distinct findings**: 16 CRIT, ~42 HIGH, ~58 MED, ~34 LOW.

Top themes:

1. **Identity model is partially fictional.** `__entity_name__` override (the 0.0.8 headline feature, commit `a3964ab`) is ignored in 7+ code paths — Walker ID construction, GraphContext ID validation/regeneration, Node neighbor queries, Edge filtering, ObjectPager metadata. Today, any class using `__entity_name__` to disambiguate from a same-`__name__` peer will have its IDs **silently rewritten back to `cls.__name__`** by `GraphContext.save_object`. **This is a data-integrity bug for the feature shipped two commits ago.**
2. **Walker protection is partially fictional.** SPEC §6.3 promises `max_steps`, `max_visits_per_node`, `max_execution_time`, `max_queue_size`. In practice: `WalkerTrail` ignores `max_trail_length` entirely; queue insert paths (`prepend`, `add_next`, `insert_after`, `insert_before`) bypass `max_size`; queue drops are silent (no log); `resume()` resets step/visit counters and restarts the wall-clock timer on every call; and `ProtectionViolation` is swallowed into `walker.report` rather than raised as `InfiniteLoopError` / `WalkerTimeoutError`.
3. **Async contract has real holes, mostly in JsonDB.** Five CRITs: webhook walker `enhanced_init` is `async def __init__` (Python ignores; coroutine leaks every construction), webhook `endpoint_func(**kwargs)` is unawaited, storage `delete_file` unawaited, two `Path.write_text` calls inside `async def` graph exporters. Plus a string of `path.exists()` / `path.glob()` sync stats inside JsonDB `async` methods that block the event loop.
4. **Storage path traversal in `LocalFileInterface` versioning methods.** Primary save/read/delete go through `PathSanitizer`; the versioning subpaths (`create_version`, `get_version`, `list_versions`, `delete_version`, `get_latest_version`) compute `root_dir / f"{file_path}.versions"` without sanitization — user-controlled `file_path` like `../../etc/passwd` escapes the storage root.
5. **Webhook HMAC verification is broken.** A 7-character slice bug in `webhook_auth.utils.verify_signature` makes `hmac.compare_digest` always compare a 64-char hex digest to a 57-char prefix → always False. Webhook signature auth currently rejects every request.
6. **SHA-256 fallback uses `==`, not `compare_digest`.** `AuthenticationService._verify_refresh_token` falls back to `hashlib.sha256(token) == hashed` when bcrypt/argon2 fail to import; this path covers refresh tokens AND password-reset tokens. CLAUDE.md §2 non-negotiable.
7. **DynamoDB throttle-retry is partial.** Only `save`/`get`/`delete` are wrapped. `find` / `count` / `batch_get` / `batch_write` surface `ProvisionedThroughputExceededException` directly to callers, even though the adapter claims throttle retry (SPEC §4.3).
8. **Env-var allowlist is not enforced.** SPEC §10.2 promises "Unknown `JVSPATIAL_*` keys are rejected at startup to catch typos." `env_adapter.py` only *reads* enumerated keys; it never *scans* the environment for stray `JVSPATIAL_*` and rejects. Plus three divergent `parse_bool` implementations across `env.py` / `env_adapter.py` / `runtime/serverless.py`.

These are listed below with file:line citations and one-line fixes. The audit was non-destructive — no fixes applied. The findings inform the next milestone.

---

## How to read this

- **Sections** are by dimension (async, security, database, walker, serverless).
- **Within a section**, findings sorted by severity then file.
- **`Cite`** column references SPEC §, CLAUDE.md §, or ROADMAP §.
- **`Fix`** is the smallest change that closes the gap, not necessarily the best long-term fix.

When the same root cause shows up in multiple dimensions, it is listed once (under the most specific dimension) and cross-referenced.

---

## 1. Identity Model — `__entity_name__` Coverage Gap

The most important class of findings. SPEC §1.2: `__entity_name__` is per-subclass; ID construction and queries must go through `_entity_name()`. Commit `a3964ab` added the override but did not update every consumer.

| # | Sev | File:Line | Problem | Fix | Cite |
|---|---|---|---|---|---|
| 1.1 | CRIT | `core/entities/walker.py:308` | `generate_id(type_code, self.__class__.__name__)` — walker IDs ignore `__entity_name__`. | `self.__class__._entity_name()` (must add classmethod to Walker; Walker does not subclass Object). | SPEC §1.2 |
| 1.2 | CRIT | `core/entities/walker.py:311` | `kwargs["entity"] = self.__class__.__name__` — persisted `entity` field ignores override. | Same as 1.1. | SPEC §1.2 |
| 1.3 | CRIT | `core/context.py:753` | ID-format check `id_parts[1] != entity.__class__.__name__` triggers regeneration for every save of any entity using `__entity_name__` override — clobbers correct IDs. | Compare against `entity.__class__._entity_name()`. | SPEC §1.2 |
| 1.4 | CRIT | `core/context.py:759` | Regeneration uses `entity.__class__.__name__` → rewrites IDs to wrong discriminator on save. | Use `_entity_name()`. | SPEC §1.2 |
| 1.5 | CRIT | `core/context.py:1403` | `find_edges_between`: `query["entity"] = edge_class.__name__` — won't find edges whose stored entity uses override. | Use `edge_class._entity_name()`. | SPEC §1.2 |
| 1.6 | HIGH | `core/entities/node.py:561, 593` | `_node_query` filters edges by `edge_filter.__name__` against persisted `entity` field → silent no-op for override classes. | Use `"entity": edge_filter._entity_name()`. | SPEC §1.2, §2.3 |
| 1.7 | HIGH | `core/entities/node.py:426, 434` | `count_neighbors` fast-path uses `node.__name__` and `re.escape(entity_name)` against `n.<ClassName>.` ID pattern. | Use `node._entity_name()`. | SPEC §1.2 |
| 1.8 | HIGH | `core/entities/node.py:668, 678, 688` | `_matches_node_filter` compares `node_obj.__class__.__name__` to string filter; `nodes(node="HostApp")` won't match. | Compare against `node_obj.__class__._entity_name()`. | SPEC §1.2 |
| 1.9 | MED | `core/entities/walker.py:308-311` | Walker has no `_entity_name()` method at all (doesn't subclass Object). | Add classmethod to Walker (or extract to shared mixin). | SPEC §1.2 |
| 1.10 | MED | `core/utils.py:40-89` | `_subclass_cache` is process-global, never cleared; stale identity after module reload (tests). | Add `clear_subclass_cache()` callable from test fixtures. | SPEC §1.2 |
| 1.11 | LOW | `core/pager.py:296` | `to_dict()` reports `object_type: self.object_class.__name__` instead of `_entity_name()`. | Resolve via `getattr(cls, "_entity_name", lambda: cls.__name__)()`. | SPEC §1.2 |

---

## 2. Walker Protection Gaps

SPEC §6.3 / CLAUDE.md §9. Promised limits are partially unenforced.

| # | Sev | File:Line | Problem | Fix | Cite |
|---|---|---|---|---|---|
| 2.1 | CRIT | `core/entities/walker.py:684-687` | `run()` catch-all swallows `ProtectionViolation` into `self.report(...)` instead of raising `InfiniteLoopError` / `WalkerTimeoutError` as SPEC promises. | Re-raise protection violations (or map to documented exception types) instead of stuffing in report. | SPEC §6.3 |
| 2.2 | CRIT | `core/entities/walker.py:886, 651` | `resume()` → `run()` → `_protection.reset()` resets step/visit counters AND restarts the wall-clock timer on every resume — protection trivially bypassed by repeated pause/resume. | Split `reset()` from `start_timer_if_needed()`; only reset on `spawn()` / explicit `reset_protection()`. | SPEC §6.3 |
| 2.3 | HIGH | `core/entities/walker_components/walker_trail.py:19-30` | `WalkerTrail` has no length bound — SPEC §6.4 promises `max_trail_length` "0 = unlimited, configurable" but it's not wired. Unbounded memory growth. | Pass `max_trail_length` from Walker into `WalkerTrail.__init__`; drop oldest on overflow. | SPEC §6.4 |
| 2.4 | HIGH | `core/entities/walker_components/walker_queue.py:67-94, 135-195` | `prepend`, `add_next`, `insert_after`, `insert_before` ignore `max_size` — protection bypass via these enqueue paths. | Apply same `max_size` guard (and warning log) used by `append`/`visit`. | SPEC §6.3 |
| 2.5 | HIGH | `core/entities/walker_components/walker_queue.py:33-36, 76-85` | `visit`/`append` silently drop on `max_size` hit — SPEC says "silent drop, logged" but no log is emitted. | Emit a one-shot WARNING when first drop occurs. | SPEC §6.3 |
| 2.6 | MED | `core/entities/walker.py:74-80` | `WalkerVisitingContext.__exit__` does not wrap `set_visitor(None)` in `try/finally`; if `current_node = None` raises, `_visitor_ref` never cleared. | Restructure with explicit `try/finally`. | SPEC §6.1 |
| 2.7 | MED | `core/entities/walker.py:63-71` | `WalkerVisitingContext.__enter__` calls `record_step` + `record_visit` — but `Walker.run()` (line 671, 674) calls the same methods directly without `visiting()`. Double-counting risk for callers who use `visiting()`. | Make `run()` use `WalkerVisitingContext`; one entry point. | SPEC §6.1, §6.3 |
| 2.8 | MED | `core/entities/walker.py:117-121` | Walker uses `extra="allow"` and does NOT declare `entity` as a model field — `entity` is set as dynamic attr, `protected=True` invariant is not enforced. | Declare `entity: str = attribute(protected=True, transient=True)` on Walker. | SPEC §1.2 |
| 2.9 | LOW | `core/entities/walker.py:734-748, 797-810` | Hook errors detected by `"Node skipped" in str(e)` substring match — fragile. | Define `SkipNode` exception class, catch directly. | SPEC §6.5 |
| 2.10 | LOW | `core/entities/walker.py:308-311` | Walker doesn't enforce `type_code="w"`; kwargs can corrupt SPEC §1.1 invariant. | Force `type_code="w"`. | SPEC §1.1 |

---

## 3. Async Contract Violations

CLAUDE.md §1 / SPEC §3. Five real bugs, plus a long tail of `path.glob`/`path.exists` sync stats blocking the event loop in JsonDB.

| # | Sev | File:Line | Problem | Fix | Cite |
|---|---|---|---|---|---|
| 3.1 | CRIT | `api/integrations/webhooks/helpers.py:135` | `enhanced_init` defined as `async def __init__`; Python ignores async-ness on `__init__`; each Walker construction returns a coroutine that's never awaited and leaks. | Remove `async` keyword. | SPEC §3 |
| 3.2 | CRIT | `api/integrations/webhooks/helpers.py:217` | `iscoroutinefunction(endpoint_func)` branch calls `endpoint_func(**kwargs)` without `await`; both `if/else` arms identical. | `result = await endpoint_func(**kwargs)` in the async branch. | SPEC §3.1 |
| 3.3 | CRIT | `api/integrations/storage/service.py:159` | `self.file_interface.delete_file(file_path)` not awaited; deletion never executes. | Add `await`. | SPEC §3.1 |
| 3.4 | CRIT | `core/graph.py:174` | `Path(output_file).write_text(...)` inside `async def generate_graph_dot` blocks the event loop. | `await asyncio.to_thread(...)`. | SPEC §3.3 |
| 3.5 | CRIT | `core/graph.py:332` | Same blocking write inside `async def generate_graph_mermaid`. | Same fix. | SPEC §3.3 |
| 3.6 | HIGH | `db/jsondb.py:168, 250, 254, 286, 355, 362` | Six sync `path.exists()` / `glob()` calls inside `async` DB methods — block event loop on disk I/O. | Wrap in `asyncio.to_thread`. | SPEC §3.3 |
| 3.7 | HIGH | `storage/interfaces/local.py:561` | `list(_read_chunks())` materializes entire file inside `to_thread` — defeats streaming purpose of `stream_file`. | Queue / `run_in_executor` iterator pattern, or use `aiofiles`. | SPEC §3 |
| 3.8 | HIGH | `db/dynamodb.py:675, 775` | `asyncio.gather(*[process_batch(...)])` without `return_exceptions=True` — one batch failure cancels siblings; partial-success state lost. | Add `return_exceptions=True`, aggregate per-batch failures. | SPEC §4.1 |
| 3.9 | HIGH | `api/integrations/webhooks/middleware.py:245, 514` | `asyncio.create_task(...)` fire-and-forget without strong reference or `add_done_callback`; tasks GC'd mid-flight, exceptions dropped. | Track tasks in a set; attach error sink. | SPEC §3 |
| 3.10 | HIGH | `testing/__init__.py:610`, `async_utils/__init__.py:37` | `asyncio.gather` without `return_exceptions=True` in test harness / general helper. | Add the flag. | SPEC §3 |
| 3.11 | MED | (multiple) `core/entities/walker_components/{walker_queue,protection,walker_trail}.py` and `core/utils.py:25`, `core/context.py:1424`, `core/entities/{object,node,edge,walker}.py` (~30 sites) | Many methods declared `async def` with no `await` — false-async. Wasted context switches; not bugs, but degrade the contract. | Convert each to sync, or genuinely await something. Roll into a single PR after the CRITs/HIGHs land. | SPEC §3.2 |

(Full async list: see reviewer report. Includes WalkerQueue mutators, TraversalProtection state methods, JsonDBTransaction buffered ops, several auth and rate-limit dict mutators.)

---

## 4. Security Boundaries

SPEC §15 / CLAUDE.md §2.

| # | Sev | File:Line | Problem | Fix | Cite |
|---|---|---|---|---|---|
| 4.1 | CRIT | `api/auth/service.py:367` | `hashlib.sha256(token).hexdigest() == hashed` — refresh-token / password-reset-token hash compared with `==`. | `hmac.compare_digest(...)`. | SPEC §15.2, CLAUDE §2 |
| 4.2 | CRIT | `storage/interfaces/local.py:207, 220, 252, 260, 288, 327, 332, 333, 356` | All file-versioning methods compute `root_dir / f"{file_path}.versions"` without `PathSanitizer`; user-controlled `file_path` escapes the storage root. | Sanitize `file_path` through `_get_full_path()` before building versioned paths; resolve and `.relative_to(self.root_dir)` the result. | SPEC §15.1 |
| 4.3 | CRIT | `api/integrations/webhooks/utils.py:176` | `hmac.compare_digest(signature, expected_signature[len(prefix):])` — `expected_signature` is the bare hex digest; slicing 7 chars produces 57-char string vs 64-char signature → always False. Webhook HMAC always rejects. | Drop the slice: `compare_digest(signature, expected_signature)`. | SPEC §15.2 |
| 4.4 | HIGH | `api/auth/api_key_service.py:30` | `self.context = context or get_default_context()` — auth state can land on non-prime DB when a caller forgets to pass `context`. | `context or GraphContext(database=get_prime_database())`. | SPEC §9, CLAUDE §1 |
| 4.5 | HIGH | `api/auth/api_key_service.py:213-246` + `api/integrations/webhooks/webhook_auth.py:19-21, 180-183` | `revoke_key` flips `is_active=False` in DB but does not invalidate the 300s in-memory `_API_KEY_CACHE`. Revoked key authenticates for up to 5 minutes after revocation. | Add `webhook_auth.invalidate_cache(...)` hook called from `revoke_key`; or re-check `is_active` on cache hit. | SPEC §15.2 |
| 4.6 | HIGH | `api/components/auth_configurator.py:175-391` | `/auth/register`, `/auth/login`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/change-password` registered without endpoint rate-limit configs; fallback is global `default_limit=60/60s` if rate limiting is enabled at all. | Hard-code rate-limit configs during `_register_auth_endpoints`; document rate-limit middleware as required when auth enabled. | SPEC §15 |
| 4.7 | HIGH | `api/integrations/webhooks/webhook_auth.py:19, 147-183` | `_API_KEY_CACHE` mutated across `await` without lock; eviction at size cap races with reads (`KeyError`). | Wrap in `asyncio.Lock`, or use bounded LRU with single-lock guard. | CLAUDE.md "race conditions in auth state" |
| 4.8 | HIGH | `api/auth/enhanced.py:235-389` | `SessionManager._sessions` / `_user_sessions` mutated across `await` without lock; concurrent logout-vs-login → `RuntimeError: dictionary changed size during iteration`; `max_sessions_per_user` enforcement is racy. | `asyncio.Lock` around session create/invalidate/cleanup. | CLAUDE.md races |
| 4.9 | HIGH | `storage/interfaces/local.py:657-659` | `get_metadata` MIME detection passes `content=b""` — falls back to extension-based `mimetypes.guess_type`; mislabels served `Content-Type`. | Read first 4 KiB of file, pass as content; or store validated MIME in sidecar at save. | SPEC §15.1 |
| 4.10 | HIGH | `api/components/error_handler.py:763, 769-770` | If operator sets `JVSPATIAL_EXPOSE_ERROR_DETAILS=true` in production, raw exception messages leak in 500 responses; safe default exists but no guard. | Refuse to honor the flag when `get_environment_mode() == "production"`. | SPEC §15.5 |
| 4.11 | MED | `api/auth/service.py:427` | Debug log discloses JWT secret length. | Log `secret_configured=bool(secret)` only. | SPEC §15.5 |
| 4.12 | MED | `api/middleware/manager.py:194-197` + `api/config_groups.py:66-75` | `CORSConfig` accepts wildcard origins; no startup validator. SPEC says wildcards must trigger startup warning. | Add validator on `CORSConfig` to warn on `"*"`; fail loudly if `allow_credentials=True` + wildcard. | SPEC §15.4 |
| 4.13 | MED | `api/auth/service.py:1052-1059` | `validate_token` warning logs the DB `base_path` — discloses internal filesystem path. | Log `db_type=type(database).__name__`. | SPEC §15.5 |
| 4.14 | MED | `api/auth/service.py:1038-1049` | DB-error fallback in `validate_token` trusts JWT-payload roles when DB lookup fails — fails open on DB outage, within JWT-expiry window. | Fail closed: return `None` on DB error. | SPEC §9 |
| 4.15 | MED | `api/auth/service.py:469-531` | `_blacklist_cache` dict mutated across `await` without lock; unbounded growth (per-entry TTL only). | Add `asyncio.Lock` + size cap with LRU eviction. | CLAUDE.md races |
| 4.16 | LOW | `api/deferred_invoke_route.py:28-37` | Empty `JVSPATIAL_DEFERRED_INVOKE_SECRET` returns `True` from `_deferred_invoke_secret_ok` — misconfigured deployment exposes internal endpoint. | Treat empty secret as "deny all". | SPEC §15.2 |
| 4.17 | LOW | `api/auth/service.py:331, 243-244` | `JVSPATIAL_AUTH_STRICT_HASHING` defaults True for passwords, False for tokens — asymmetry surprising. | Apply strict to both; document rationale. | SPEC §15.5 |
| 4.18 | LOW | `storage/interfaces/local.py:194-196` | Windows reserved names (CON, AUX, NUL) pass `SAFE_FILENAME_PATTERN`. | Add Windows-reserved-name check. | SPEC §15.1 |

---

## 5. Database Adapter Parity

SPEC §4-5 / ROADMAP §2.2, §2.4.

| # | Sev | File:Line | Problem | Fix | Cite |
|---|---|---|---|---|---|
| 5.1 | CRIT | `db/dynamodb.py:1052-1064, 1194-1265, 668-684, 770-778` | DynamoDB throttle retry (`_run_with_throttle_retry`) covers only `save`/`get`/`delete`. `find` / `count` / `batch_get` / `batch_write` surface `ProvisionedThroughputExceededException` immediately. | Wrap all CRUD paths in throttle retry; escalate `batch_write` inner-retry to the shared envelope. | SPEC §4.3 |
| 5.2 | HIGH | `db/query.py:425-426, 502-520, 559-564, 663-679` | `QueryBuilder` exposes `nor_`, `mod`, `all_`, `regex`, `type_`, `size`, `$nor`, `$mod`, `$type`, `$all`, `$where`, `$text` — but `QueryEngine._match_value` returns `False` for any unknown operator; `match` never branches on `$nor`. Queries built via the builder silently match nothing. | Implement the operators in `_match_value`/`match`, OR have builder + engine raise `QueryError("unsupported operator")`. | SPEC §5.1 |
| 5.3 | HIGH | `db/database.py:279-322`, `db/work_claim.py:53-62` | Default `find_one_and_update` / `find_one_and_delete` query on `_id`, but JsonDB/SQLite/DynamoDB persist only `id`; silent miss on non-Mongo backends. | Normalize `_id` ↔ `id` in default impls, or override on each backend. | SPEC §4.1 |
| 5.4 | HIGH | `db/database.py:144-159` | `Database.count` default materializes every record via `find`. Third-party adapters registered via `register_database_type` inherit this — silent OOM on large collections. | Either mark `count` abstract, or warn once-per-class on hit. | SPEC §4.1 |
| 5.5 | HIGH | `db/mongodb.py:332-351, 380-401` | `find_many` and `bulk_save` reconnect-retry once but escaping raw `PyMongoError` is not wrapped in `DatabaseError` (CRUD paths are wrapped). | Route through `_run_with_reconnect`. | SPEC §4.1, §4.3 |
| 5.6 | HIGH | `db/database.py:212-250` | Default `bulk_save` does sequential `save()` without per-record exception handling — partial-success leaves DB in unobservable state. Doc claims "all-or-throw" but JsonDB override logs and continues. | Return `(saved, failed_ids)` or document loudly + reconcile JsonDB override. | SPEC §4.1 |
| 5.7 | MED | `db/dynamodb.py:686-778` | `batch_write` inner retry — at most 3 attempts then logs warning and returns success. Lost writes silent. | Return actual saved count, propagate through `bulk_save`, raise on persistent unprocessed items. | SPEC §4.1 |
| 5.8 | MED | `db/query.py:170-196` | `_add_indexing_hints` mutates the cached optimized query in-place; subsequent callers receive same dict. Also `$hint` falls through in non-Mongo backends → match returns False. | Deep-copy on cache hit; whitelist-skip `$hint`/`$select` in `_match_value`. | SPEC §5.3 |
| 5.9 | MED | `db/transaction.py:122-194`, `db/mongodb.py:67, 699-733` | `MongoDB.supports_transactions = True` unconditionally; `begin_transaction` returns `None` when not on a replica set. Flag is dishonest. | Probe replica-set support lazily; cache; or rename flag and add `is_transactional()`. | SPEC §4.2 |
| 5.10 | MED | `db/sqlite.py:34-64, 117-162` | One persistent connection per `SQLiteDB` instance; no cross-loop detection (MongoDB has one). Use across multiple event loops fails silently. | Track creating loop in `__init__`; rebind on detection or raise `DatabaseError`. | SPEC §4.3 |
| 5.11 | MED | `db/_sqlite_translate.py:86-98` | `_safe_field_path` regex rejects digit-only segments (e.g. `arr.0.value`); query silently falls back to full scan + Python match. | Widen segment regex, OR log debug on fallback so slow queries are diagnosable. | SPEC §5.2 |
| 5.12 | MED | `db/dynamodb.py:1066-1265` | `find()` fallback to `Scan` does not push `$or`/`$and`/`$gt` into FilterExpression; full client-side scan + match. | Push to FilterExpression where supported. | SPEC §5.2 |
| 5.13 | LOW | `db/database.py:212-250` and adapter overrides | `bulk_save` returns `int` everywhere; callers cannot distinguish SQLite all-or-nothing vs DynamoDB silent drop. | Expose `BulkSaveResult(attempted, saved, failed_ids)` (or sibling `bulk_save_detailed`). | SPEC §4.1 |
| 5.14 | LOW | `db/transaction.py:363-413` | `JSONTransaction` is dead code; `JsonDBTransaction` replaces it; still in `__all__`. | Remove or `@deprecated`. | ROADMAP §2.9 |
| 5.15 | LOW | `db/sqlite.py:260-285` | `save()` and `bulk_save` differ in `id` coercion (`record.setdefault("id", uuid)` vs `str(r["id"])`). Inconsistent get-by-id. | Force `record["id"] = str(record["id"])` after setdefault. | SPEC §4.1 |

(Plus minor LOWs on log hygiene, dead glob filters in JsonDB, double cache writes in `CachingDatabase.find_one_and_update`.)

---

## 6. Inheritance, Subclass Init, and Library Self-Discipline

| # | Sev | File:Line | Problem | Fix | Cite |
|---|---|---|---|---|---|
| 6.1 | HIGH | `core/entities/node.py:62-118` | `Node.__init_subclass__` does NOT call `super().__init_subclass__()` — `AttributeMixin.__init_subclass__` never runs for Node subclasses; `_PROTECTED_ATTRS` registration skipped. | Add `super().__init_subclass__(**kwargs)` at top. | SPEC §2.5 |
| 6.2 | HIGH | `core/entities/edge.py:66-123` | Same: `Edge.__init_subclass__` skips `super()`. | Same fix. | SPEC §2.5 |
| 6.3 | HIGH | `core/entities/walker.py:366-396` | Same: `Walker.__init_subclass__` skips `super()`. | Same fix. | SPEC §2.5 |
| 6.4 | HIGH | `core/entities/root.py:19` | `_lock = asyncio.Lock()` is `ClassVar` — single global lock across all GraphContexts and event loops; "different loop" errors under per-test loop fixtures; SPEC §1.3 implies per-context. | Lock per `GraphContext` (e.g. lazy-init dict keyed by `id(context)`). | SPEC §1.3, §7.2 |
| 6.5 | HIGH | `core/entities/root.py:100` | `object.__setattr__(self, "id", "n.Root.root")` — library bypasses its own `protected=True`. | `_unsafe_set_id` helper, or check/clear `_initializing` and route through normal setter. | CLAUDE §5 |
| 6.6 | HIGH | `core/context.py:761, 812, 818, 1229` | Six `object.__setattr__` call sites bypass protected-attribute enforcement (id, edge_ids, atomic_increment). | Route through `AttributeMixin.__setattr__` with explicit override flag. | CLAUDE §5 |
| 6.7 | MED | `core/mixins/deferred_save.py:119+` | No runtime check of MRO order — wrong order silently disables batching (CLAUDE.md warns but library doesn't detect). | In `__init_subclass__`, assert mixin precedes persistable base; warn or raise. | CLAUDE §6 |
| 6.8 | MED | `core/entities/object.py:112-140` | `__setattr__` allows ANY `name.startswith("_")` — callers can attach arbitrary `_foo` attributes, bypassing schema validation (SPEC promises rejection). | Restrict private bypass to declared `__private_attributes__` + `_initializing`. | SPEC §2.1 |
| 6.9 | MED | `core/events.py:36, 119`, `core/context.py:1818-1843` | `EventBus._lock` and `event_bus` module global bound to import-time loop; tests with new loops fail. Also `get_default_context()` has check-and-set race. | Lazy-init locks per first-async-use; use `ContextVar.get` + token for default context init. | SPEC §6.x, §7.1 |
| 6.10 | MED | `core/events.py:38-45` | `register_entity` on `walker.spawn()` has no symmetric `unregister_entity` — events keep firing to done walkers; weakref GC only. | Call `event_bus.unregister_entity(self.id)` in `disengage()` and end-of-`spawn`. | SPEC §6.x |
| 6.11 | MED | `core/entities/walker_components/protection.py:108-115` | `_check_timeout` reads `_start_time` then computes elapsed; concurrent `reset()` corrupts. | Snapshot to local before subtraction. | SPEC §6.3 |

---

## 7. Serverless / Config / Stability Discipline

SPEC §10-11, §18 / CLAUDE.md §4, §7, §8.

| # | Sev | File:Line | Problem | Fix | Cite |
|---|---|---|---|---|---|
| 7.1 | HIGH | `env_adapter.py:52-193` | Allowlist not enforced. SPEC §10.2 promises "Unknown `JVSPATIAL_*` keys are rejected at startup." Adapter only *reads* enumerated keys; never *scans* for stray `JVSPATIAL_*`. | Add startup validator: scan `os.environ` for `JVSPATIAL_*` prefix; reject unknowns. | SPEC §10.2 |
| 7.2 | HIGH | `env_adapter.py:11` vs `env.py:36-43` vs `runtime/serverless.py:11` | Three divergent `parse_bool` implementations. `JVSPATIAL_DEBUG=on` parses different ways in different code paths. | Consolidate on `env.parse_bool`; have others import. | SPEC §10.2 |
| 7.3 | MED | `env_adapter.py:11`, `runtime/serverless.py:11` | `_parse_bool` non-strict; `JVSPATIAL_DEBUG=garbage` silently maps to False with no validation error. Hides typos. | Raise `ValueError` on unrecognized non-empty. | SPEC §10.2 |
| 7.4 | MED | `serverless/deferred_invoke.py:52-73` | `normalize_deferred_envelope` covers flat Lambda invoke + SQS scheduler shapes only. Direct Lambda SQS-batch trigger (`{"Records": [...]}`) raises. | Accept `Records[...]` and dispatch per-record, OR document the unwrap requirement. | SPEC §11.3 |
| 7.5 | MED | `.env.example:94-106` vs `api/config_groups.py:66-81` | `.env.example` documents `JVSPATIAL_CORS_ORIGINS=*` with "Default: *" — actual default is localhost whitelist. Following docs degrades security. | Update `.env.example`; add production-only note. | CLAUDE §8 |
| 7.6 | MED | `runtime/lwa.py:107-110` (called from `server.py:137`) | LWA env defaults applied inside `Server.__init__`; LWA reads them before Python starts. The docstring acknowledges this; the practical effect is zero for the actual LWA bootstrap. | Downgrade to operator warning, or remove and document IaC-only. | SPEC §11.4 |
| 7.7 | MED | `db/transaction.py:243-249` | `JsonDBTransaction(best_effort=True)` imports private `_emit_once` from `jvspatial.utils.stability` — internal symbol crossed module boundary. | Expose public `emit_experimental_once(...)`. | SPEC §18 |
| 7.8 | MED | `serverless/deferred_invoke.py:1-88` | Handlers registered post-import → race: request arriving before user modules import returns 404 `UnknownDeferredTaskError`. Not silently dropped (good); but no startup-readiness log. | Log registered handlers on startup, or log debug on empty-registry first-dispatch. | SPEC §11.3 |
| 7.9 | LOW | `env_adapter.py:39-49` | `deep_merge` silently skips `None` in override; `Server(host=None, ...)` does NOT override env. Surprising. | Document; or sentinel-based override. | SPEC §10.2 |
| 7.10 | LOW | `api/auth/service.py:164-170` | `AuthenticationService` captures `is_serverless_mode()` and `_bcrypt_rounds` at construction; per-test mode flips require service rebuild + `reset_serverless_mode_cache()`. | Note in CLAUDE.md §4 (test guidance). | CLAUDE §4 |
| 7.11 | LOW | `runtime/lwa.py:18-23` | `_deferred_invoke_pass_through_path` reads `JVSPATIAL_API_PREFIX` directly, bypassing `resolve_api_prefix()`. Two divergent reads. | Use `resolve_api_prefix()`. | SPEC §10.4 |
| 7.12 | LOW | `api/components/app_builder.py:58-65` | `JVSPATIAL_DOCS_DISABLED` parses with ad-hoc inline set `{"1","true","yes","on"}` — fourth divergent bool parser. | Use `env.parse_bool`. | SPEC §10.5 |
| 7.13 | LOW | `api/middleware/manager.py:54-59` | `_DOCS_PATH_PREFIXES = ("/docs", "/redoc", "/openapi.json")` hardcoded — customizing `docs_url` breaks Swagger UI via strict CSP. | Derive from `config.docs_url`/`redoc_url`/`openapi_url`. | SPEC §10.5 |
| 7.14 | LOW | `serverless/tasks/stub.py:27` | `LoggingNoopTaskScheduler.schedule()` logs warning per call. CloudWatch cost in misconfigured serverless deploys. | Downgrade per-call to debug; rely on once-per-process error. | SPEC §11.2 |
| 7.15 | LOW | `serverless/factory.py:73-80` | Fallback to `LoggingNoopTaskScheduler` when AWS deferred-task config missing — warning string only; no startup error in non-`strict` mode. | Once-per-process startup error log when serverless + provider=aws and config missing. | SPEC §11.3 |

---

## 8. ObjectPager / Pagination

| # | Sev | File:Line | Problem | Fix | Cite |
|---|---|---|---|---|---|
| 8.1 | HIGH | `core/pager.py:118-144` | Keyset pagination filters `id > after_id` but sorts by `context.<order_by>` — cursor doesn't track sort key; wrong/missing rows on writes between pages. | Disallow `order_by` with `after_id`, OR include order field in cursor. | SPEC §5 |
| 8.2 | HIGH | `core/pager.py:73, 142, 214` | `_cache` keyed by `(page, hash(filters))` and never invalidated — stale results after writes. | Drop the cache or expose `invalidate()`. | SPEC §5 |

---

## 9. Verified Correct (no findings)

These are explicitly checked — the audit found no gap. Listed so future reviewers know the area was inspected:

- **Detection precedence in `is_serverless_mode`** (SPEC §11.1) — exact match.
- **`reset_serverless_mode_cache`** clears both lru_caches.
- **Mode-dependent defaults read mode at call time**, not at import.
- **`JVSPATIAL_DOCS_DISABLED` coverage**: all four URLs (`docs_url`, `redoc_url`, `openapi_url`, `swagger_ui_oauth2_redirect_url`) set to None.
- **CSP per-path match** uses exact-or-segment matching; `/docsfoo` correctly stays on strict CSP.
- **bcrypt rounds**: serverless=10, standard=12, env-overridable.
- **JsonDB `/tmp` default**: only applied under serverless mode.
- **`__init__.py` `__all__`**: every imported public symbol is in `__all__`; no underscore-module imports leak to public surface.
- **`Server.run()` blocking**: `uvicorn.run()` is the only blocking call; `run_async()` uses async `serve()`.
- **JWT secret validation**: rejected if empty or known-insecure default.
- **CSP defaults**: strict on app routes; relaxed only on docs paths.
- **JsonDB atomic writes**: every write path goes through `_atomic.atomic_write_bytes`; no direct `open().write()` bypasses.
- **PathLock coverage in JsonDB**: every record write/delete acquires the per-file lock.
- **SQLite Mongo→SQL translator escape hygiene**: values bound, field paths regex-validated, unknown ops trigger fallback (parameterized, no injection).
- **Auth state on prime DB** in `AuthenticationService` (one drift in `APIKeyService` flagged separately at 4.4).
- **Primary file save/read/delete in `LocalFileInterface`** correctly use `PathSanitizer` + `resolve()` + `relative_to(root_dir)`. The escape vector is exclusively in versioning methods (4.2).
- **`hmac.compare_digest`** used everywhere SPEC §15.2 lists, **except** the SHA-256 fallback (4.1) and the broken-by-slice webhook signature path (4.3).

---

## 10. Recommended Remediation Sequence

Roughly ordered by blast radius × cost. CRITs first, then HIGHs that block CRIT fixes.

### Wave 1 — restore the contracts the library claims to provide (1-2 weeks)

1. **Identity model** (§1.1-1.5): patch all 5 CRIT call sites to use `_entity_name()`. Add classmethod to Walker. Add regression test that subclasses with `__entity_name__` round-trip through save/load.
2. **Walker protection** (§2.1-2.5): make `ProtectionViolation` raise documented exception types; separate timer-start from counter-reset; wire `max_trail_length`; cap insert paths; emit drop warnings.
3. **Async CRITs** (§3.1-3.5): five surgical fixes. Add tests that assert coroutine results are not leaked.
4. **Security CRITs** (§4.1-4.3): one `compare_digest` fix; three sanitizer calls in versioning paths; one slice removal in webhook verifier.
5. **DynamoDB throttle retry** (§5.1): wrap the four uncovered code paths in `_run_with_throttle_retry`.

### Wave 2 — close the HIGHs that hide bugs (1-2 weeks)

6. **JsonDB sync stats** (§3.6): six `to_thread` wraps. Bench to confirm regression budget.
7. **`__init_subclass__` super-chains** (§6.1-6.3): three one-line additions. Add regression test that protected attrs are registered on Node/Edge/Walker subclasses.
8. **Auth races + cache invalidation** (§4.5-4.8): four `asyncio.Lock`s. Add concurrent-stress test.
9. **Pager + cache** (§8.1-8.2): drop the stale cache; constrain or fix keyset pagination.
10. **Default `find_one_and_update` `_id` vs `id`** (§5.3): normalize in default impls.

### Wave 3 — close the latent timebombs (2-4 weeks)

11. **Env allowlist enforcement + parse_bool consolidation** (§7.1-7.2): both small, both gate a class of future config-typo bugs.
12. **`bulk_save` partial-success semantics** (§5.6, 5.7): unify return type across adapters.
13. **MongoDB `supports_transactions` honesty** (§5.9): probe replica set; rename or runtime-check.
14. **QueryBuilder ↔ QueryEngine operator parity** (§5.2): implement or reject.
15. **CORS wildcard startup warning** (§4.12), **`JVSPATIAL_EXPOSE_ERROR_DETAILS` production guard** (§4.10).

### Wave 4 — cleanup, parity, polish (ongoing)

16. False-async cleanup (§3.11): roll-up PR converting 30+ `async def` with no `await` to `def`. Or accept and document.
17. SQLite cross-loop detection (§5.10).
18. Stability-tier cleanup (§7.7 expose `emit_experimental_once`; §7.13 docs-prefix derivation from config).
19. Dead code (§5.14 `JSONTransaction`).
20. LOW hygiene findings (log content sanitization, Windows-reserved-name filename check, `.env.example` accuracy).

---

## Appendix — Reviewer Reports

Five reviewers produced this audit:
1. **Async contract**: agent `a85870fd5ef8e1790`
2. **Security boundaries**: agent `a27d75965d59e33a0`
3. **DB adapter parity**: agent `ac27d884ad66bfd59`
4. **Walker / identity / invariants**: agent `a716803cafeda1acb`
5. **Serverless / config / stability**: agent `a7842dedd5dfe62d4`

Full reports are in the agent transcripts. This file synthesizes and de-duplicates their findings; for the raw lists with extended rationale, query the agents above via SendMessage.
