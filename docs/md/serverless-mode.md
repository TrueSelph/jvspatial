# Serverless Mode

`jvspatial` supports a serverless adaptation mode designed for AWS Lambda-first deployments.

## Enablement

- Explicit: set `SERVERLESS_MODE=true`
- Auto-detected: AWS Lambda via `AWS_LAMBDA_RUNTIME_API` or `AWS_LAMBDA_FUNCTION_NAME`
- **`Server.config.serverless_mode`**: When you omit an explicit config argument, `is_serverless_mode()` also consults `get_current_server().config` (set by `Server` / `set_current_server`). Keep `SERVERLESS_MODE` in sync with `ServerConfig.serverless_mode` in processes that never call `set_current_server`, or rely on this context so webhook middleware and libraries agree.

## Behavior Changes

- Background fire-and-forget behavior is disabled for request-bound flows.
- Webhook async queue response path is bypassed; handlers execute inline.
- Scheduler thread lifecycle hooks are disabled.
- JSON/SQLite and local file storage defaults prefer `/tmp` paths.
- **Deferred saves** (`DeferredSaveMixin`) are forced off: every `save()` persists immediately regardless of `JVSPATIAL_ENABLE_DEFERRED_SAVES`. Use `deferred_saves_globally_allowed()` for the effective check. Call `await entity.flush()` or `flush_deferred_entities(...)` at the end of a request as usual; they remain no-ops for dirty state when deferral was inactive.

## Migration Notes

- `BACKGROUND_PROCESSING` has been removed.
- Use `SERVERLESS_MODE` and `is_serverless_mode()` for runtime checks.
- If you relied on local persistent paths, move to durable storage (MongoDB/S3) or explicitly configure writable ephemeral `/tmp`.

## `create_task` — unified background work API

`jvspatial.create_task` is an **async** function and the standard interface for scheduling or running background work. **Always** call it with `await` from `async def` code.

### Shape A — registered handler (serverless-safe)

```python
from jvspatial import create_task

await create_task("my.task_type", {"key": "value"}, run_at=time.time() + 5)
```

- **Non-serverless**: sleeps then calls the registered deferred-invoke handler in-process via `asyncio.create_task`; returns that `Task`.
- **Serverless**: delegates to the cloud task scheduler (`dispatch_deferred_task`); returns `None`.

### Shape B — raw coroutine (default)

```python
await create_task(some_coroutine(), name="worker")
```

- **Non-serverless**: `asyncio.create_task` with automatic exception logging on failure; returns the `Task` (fire-and-forget unless you await it).
- **Serverless**: **awaits** the coroutine in the current request and returns `None`. Use this so request-scoped work actually runs on Lambda.

You can branch on the return value: `None` means the coroutine ran inline (serverless) or only deferred dispatch ran (Shape A serverless); a `Task` means work was scheduled locally.

### Shape B — `concurrent=True`

When you need a real background `Task` in **both** environments (for example SSE streaming that polls `task.done()` while other work runs), pass `concurrent=True`:

```python
task = await create_task(walker.spawn(agent), name="stream", concurrent=True)
```

Uses `asyncio.create_task` even on serverless; the task may not outlive the invocation.

For durable or cross-invocation work on serverless, prefer **Shape A** instead of awaiting a large coroutine inline.

### Deferred task schedulers

Serverless runtimes cannot rely on `asyncio.create_task` for work that must continue after the handler returns. Shape A uses **`get_task_scheduler()`** / **`dispatch_deferred_task()`** (from `jvspatial.serverless.factory`) to enqueue JSON-serializable work.

- **Not serverless**: the default scheduler is a no-op unless you pass a sync executor to `NoopOrSyncScheduler` or use `override=`.
- **AWS**: By default, if `AWS_LAMBDA_FUNCTION_NAME` is set, tasks are sent with **Lambda async invoke** (`InvocationType=Event`). **EventBridge Scheduler** one-shot schedules apply when `run_at` is set, EventBridge is enabled, and role/ARN requirements are satisfied (see below).
- **SQS**: Set `JVSPATIAL_AWS_DEFERRED_TRANSPORT=sqs` and `JVSPATIAL_AWS_SQS_QUEUE_URL`; you must run a worker that consumes messages. Messages use a nested `payload` object. Before calling `dispatch_deferred_invoke`, flatten with **`normalize_deferred_envelope`** (exported from `jvspatial`) so the body matches the Lambda/LWA shape.
- **Strict dispatch**: `create_task("…", {}, strict=True)` (or `dispatch_deferred_task(..., strict=True)`) raises `RuntimeError` if serverless mode is on but the resolved scheduler is a logging no-op. Otherwise the first no-op schedule in serverless mode emits a one-time **error** log.
- **Provider override**: `JVSPATIAL_DEFERRED_TASK_PROVIDER` (`aws`, `azure`, `gcp`, `vercel`, `auto`) or `Config.deferred_task_provider` / `ServerConfig.deferred_task_provider`.
- **Detection**: `detect_serverless_provider()` complements `is_serverless_mode()` for choosing a backend.

EventBridge (avoids relying on delayed Lambda invoke for timed `run_at` work) uses **`JVSPATIAL_EVENTBRIDGE_*`**:

- `JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED` — if **unset** on serverless AWS when `Server` starts, `apply_aws_eventbridge_env_default()` sets it to **`true`** only when prerequisites are met (non-empty `JVSPATIAL_EVENTBRIDGE_ROLE_ARN` and a resolvable Lambda target: either `JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN` or `AWS_LAMBDA_FUNCTION_NAME` + `AWS_ACCOUNT_ID` + region from `AWS_REGION` / `AWS_DEFAULT_REGION`). Otherwise it sets **`false`** so cold start succeeds; timed `run_at` work then uses Lambda async invoke. If the variable is **already set** in the environment, it is never changed. Set `false` explicitly to force Lambda-only behavior.
- `JVSPATIAL_EVENTBRIDGE_ROLE_ARN` — **required** for schedules to be created (IAM role EventBridge Scheduler uses to invoke your function).
- `JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN` — optional; if unset, the target ARN is built from `AWS_LAMBDA_FUNCTION_NAME` + `AWS_REGION` (or `AWS_DEFAULT_REGION`) + `AWS_ACCOUNT_ID` when all are set (same rule as `jvspatial.runtime.eventbridge_readiness`).
- `JVSPATIAL_EVENTBRIDGE_SCHEDULER_GROUP` (default `default`)

This is separate from the **periodic** `SchedulerService` (`schedule` package + background thread), which remains disabled in serverless mode.

## Work-claim helpers

`jvspatial` provides DB-agnostic lease-based helpers for durable background processing:

```python
from jvspatial import claim_record, release_claim, delete_claimed_record

doc, token = await claim_record(db, "my_collection", record_id)
# ... process doc ...
await delete_claimed_record(db, "my_collection", record_id, token)
```

- **`claim_record`**: atomically sets `_jv_claim` + `_jv_claim_until` so only one worker processes a record. Returns `(stripped_doc, token)` on success, `(None, None)` if already claimed or not found.
- **`release_claim`**: releases the lease without deleting the record (use on error).
- **`delete_claimed_record`**: deletes the record only if the token still matches.
- Lease TTL: `JVSPATIAL_WORK_CLAIM_STALE_SECONDS` (default 600). After this period a crashed claim can be re-acquired.

### Lambda Web Adapter (LWA) and the deferred HTTP entrypoint

Direct Lambda invocations (async invoke and EventBridge targets) deliver a JSON body that includes **`task_type`** plus task-specific fields. The [Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter) can forward that payload to your FastAPI app as an HTTP `POST`.

- **Canonical path**: `{JVSPATIAL_API_PREFIX}/_internal/deferred` (default **`/api/_internal/deferred`**), exposed by `register_deferred_invoke_route()` when core routes are registered (`AppBuilder.register_core_routes`). If you assemble a `FastAPI` app without that path, call `jvspatial.api.deferred_invoke_route.register_deferred_invoke_route(app)` yourself.
- **Disable**: set `JVSPATIAL_DEFERRED_INVOKE_DISABLED=true` to skip registering the route (e.g. when another entrypoint handles deferred work).
- **Dispatch**: the body must be a JSON object with a string **`task_type`**. jvspatial dispatches to handlers registered via **`register_deferred_invoke_handler(task_type, fn)`** or **`@deferred_invoke_handler("…")`** (also exported from top-level **`jvspatial`**). Unknown `task_type` yields HTTP 404.
- **Auth**: The deferred HTTP path is **always exempt from `AuthenticationMiddleware`** (JWT/API key): Lambda async invoke bodies cannot carry your app’s `Authorization` header. Optional **`JVSPATIAL_DEFERRED_INVOKE_SECRET`** is checked **inside** the deferred route only. If that secret is set, each request must send the same value in **`X-JVSPATIAL-Deferred-Authorize`** or **`Authorization: Bearer <secret>`**; otherwise the route returns 401. For same-function self-invoke, leave the secret unset unless you inject headers in infra. Still prefer private network / VPC boundaries for production.
- **LWA environment (best-effort)**: when `is_serverless_mode()` is true, `detect_serverless_provider() == "aws"`, and LWA is detected (e.g. `AWS_LWA_PORT` or `AWS_LAMBDA_EXEC_WRAPPER` indicating the adapter), **`apply_aws_lwa_env_defaults()`** (`jvspatial.runtime.lwa`) runs from **`Server.__init__`** and uses `os.environ.setdefault` for **`AWS_LWA_PASS_THROUGH_PATH`** (same path rule as `{JVSPATIAL_API_PREFIX}/_internal/deferred`) and **`AWS_LWA_INVOKE_MODE=RESPONSE_STREAM`**. Set **`JVSPATIAL_LWA_ENV_DEFAULTS=true`** to force these defaults if detection misses; **`JVSPATIAL_LWA_ENV_DEFAULTS=false`** to disable. The LWA extension may still read env before Python starts, so **set them in Lambda / IaC** when you need guarantees.
- **EventBridge default (best-effort)**: when `is_serverless_mode()` is true and `detect_serverless_provider() == "aws"`, **`apply_aws_eventbridge_env_default()`** (`jvspatial.runtime.lwa`) runs from **`Server.__init__`**. If **`JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED`** is absent, it sets **`true`** or **`false`** based on whether EventBridge prerequisites are satisfied (see `jvspatial.runtime.eventbridge_readiness`). Provide **`JVSPATIAL_EVENTBRIDGE_ROLE_ARN`** and either **`JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN`** or **`AWS_LAMBDA_FUNCTION_NAME`** + **`AWS_ACCOUNT_ID`** (+ region) in IaC when you want scheduler-backed `run_at`.

Payloads from **`AwsLambdaDeferredTaskScheduler`** and EventBridge **`Input`** both include `task_type`, so they align with this router.

## AWS Deployment Tips

- Prefer MongoDB/DynamoDB/S3 for durable data.
- Keep local file/db paths under `/tmp`.
- Include secure hash dependencies (`bcrypt` or `argon2`) in deployment package.
