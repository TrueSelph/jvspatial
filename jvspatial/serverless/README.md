# jvspatial/serverless

Deferred task dispatch for serverless environments. Sister to `jvspatial/runtime` (detection).

> **Read first**: [SPEC §11](../../SPEC.md), [docs/md/serverless-mode.md](../../docs/md/serverless-mode.md)

---

## Purpose

`serverless/` provides a dispatcher for tasks that must run outside the current HTTP invocation: long-running work, retryable steps, fan-out workflows. On AWS this typically routes through Lambda async-invoke or EventBridge; the API is provider-agnostic.

## Layout

```
serverless/
├── factory.py             # dispatch_deferred_task, get_task_scheduler
├── deferred_invoke.py     # register_deferred_invoke_handler, dispatch_deferred_invoke, normalize_deferred_envelope
└── tasks/                 # Provider-specific scheduler implementations
    └── __init__.py
```

## Public API (from `jvspatial.serverless`)

| Name | What it does |
|---|---|
| `dispatch_deferred_task(task_type, payload)` | Enqueue a task for out-of-band execution |
| `get_task_scheduler()` | Return the configured scheduler instance |

Plus from `jvspatial.serverless.deferred_invoke`:

| Name | What it does |
|---|---|
| `register_deferred_invoke_handler(task_type, handler)` | Register an async handler for a task type |
| `dispatch_deferred_invoke(task_type, payload)` | Dispatch and immediately invoke registered handler (in-process testing path) |
| `normalize_deferred_envelope(event)` | Flatten provider-specific event envelopes (SQS, EventBridge) |

## Invariants

- **Handlers must be idempotent.** The framework provides no exactly-once guarantee. Retries may deliver the same payload multiple times.
- **Handler registration is process-global.** Late registration after the first dispatch is allowed but discouraged.
- **Envelope normalization is provider-aware.** New providers should extend `normalize_deferred_envelope`, not bypass it.
- **Secrets in deferred-invoke headers use constant-time comparison.** (See `deferred_invoke.py`.)
- **Lambda Web Adapter env defaults are set best-effort by `Server`** when LWA is detected. IaC should set them explicitly. (SPEC §11.4)

## Modification patterns

- **Adding a provider**: implement a scheduler in `tasks/`, register it via configuration. Extend `normalize_deferred_envelope` if the new provider has a distinct event envelope.
- **Adding a handler**: use `@deferred_invoke_handler("task.name")` or `register_deferred_invoke_handler(...)`. Document idempotency requirements at the call site.
- **Adding a new envelope flattener**: keep flattening in `normalize_deferred_envelope` rather than per-handler.

## Related docs

- [docs/md/serverless-mode.md](../../docs/md/serverless-mode.md)
- [docs/md/production-deployment.md](../../docs/md/production-deployment.md)

## Stability

`dispatch_deferred_task`, `get_task_scheduler`, `register_deferred_invoke_handler`, `dispatch_deferred_invoke`, `normalize_deferred_envelope` are stable. `tasks/` internals can change. LWA-specific env wiring in `jvspatial/runtime/lwa.py` is internal.
