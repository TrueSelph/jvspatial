# jvspatial Documentation Index

This directory holds detailed how-to and reference documentation. For higher-level orientation start at the repo root:

- [README.md](../../README.md) — project overview and installation
- [PRD.md](../../PRD.md) — *why* the library exists, target users, non-goals
- [SPEC.md](../../SPEC.md) — *what* the library guarantees (technical contract)
- [ROADMAP.md](../../ROADMAP.md) — forward direction and known gaps
- [CLAUDE.md](../../CLAUDE.md) — agent maintenance guide
- [CHANGELOG.md](../../CHANGELOG.md) — release history

The documents below answer *how* to use each subsystem. Every link resolves; entries marked **NEW** were added since the previous index revision.

---

## Getting Started

| Document | What's in it |
|---|---|
| [Quick Start Guide](quick-start-guide.md) | Minimal end-to-end setup: install, create a Server, define a Node, expose an endpoint. |
| [Examples](examples.md) | Index of runnable scripts in [examples/](../../examples/). |
| [Auth Quickstart](auth-quickstart.md) | Fast path to authenticated endpoints. |
| [Endpoint Registration Guide](endpoint-registration-guide.md) | Recommended entrypoint pattern and auto-registration semantics. |
| [Migration Guide](migration.md) | Adopting jvspatial in an existing project. |

## Core Concepts

| Document | What's in it |
|---|---|
| [Entity Reference](entity-reference.md) | `Object`, `Node`, `Edge`, `Walker`, `Root` — fields, lifecycle, persistence shape. |
| [Attribute Annotations](attribute-annotations.md) | `@attribute(protected, transient, private, indexed, …)` semantics. |
| [Graph Context](graph-context.md) | Database + cache + monitor binding; multi-database setup. |
| [Context Management Guide](context-management-guide.md) | When and how to scope `GraphContext` / `ServerContext`. |
| [Graph Traversal](graph-traversal.md) | Walker pattern, queue semantics, visit hooks. |
| [Graph Visualization](graph-visualization.md) | DOT / Mermaid export. |
| [Node Operations](node-operations.md) | Connect / disconnect / neighbor queries. |
| [Walker Events](walker-reporting-events.md) | Walker event bus and reporting. |
| [Walker Queue Operations](walker-queue-operations.md) | Queue manipulation patterns. |
| [Walker Trail Tracking](walker-trail-tracking.md) | Trail capture, metadata, summary. |
| [Infinite Walk Protection](infinite-walk-protection.md) | `max_steps` / `max_visits_per_node` / `max_execution_time`. |

## API and Server

| Document | What's in it |
|---|---|
| [REST API](rest-api.md) | Endpoint patterns and conventions. |
| [Server API](server-api.md) | `Server` configuration surface. |
| [API Architecture](api-architecture.md) | Mixin composition, request lifecycle, middleware stack. |
| [Decorator Reference](decorator-reference.md) | Every decorator the library ships: `@endpoint`, `@attribute`, `@on_visit`, etc. |
| [Pagination](pagination.md) | `ObjectPager` usage. |
| [Rate Limiting](rate-limiting.md) | **NEW** Token-bucket rate limit configuration. |
| [Error Handling](error-handling.md) | Exception taxonomy and propagation. |

## Authentication and Security

| Document | What's in it |
|---|---|
| [Authentication](authentication.md) | JWT, API key, refresh-token flows. |
| [API Keys](api-keys.md) | **NEW** Key management endpoints and hashing model. |
| [Password Migration Guide](password-migration-guide.md) | bcrypt upgrade path. |
| [Security Review](security-review.md) | **NEW** Audit findings and resolved fixes. |
| [Security Operational Notes](security-operational-notes.md) | **NEW** Runtime security guidance. |
| [Production Deployment](production-deployment.md) | **NEW** Hardening checklist for production. |

## Database and Storage

| Document | What's in it |
|---|---|
| [MongoDB Query Interface](mongodb-query-interface.md) | Mongo-style operators across all backends. |
| [Custom Database Guide](custom-database-guide.md) | Implementing and registering a new `Database` adapter. |
| [DynamoDB Guide](dynamodb-guide.md) | DynamoDB-specific setup and limits. |
| [File Storage Architecture](file-storage-architecture.md) | Storage interface, security layer, version model. |
| [File Storage Usage](file-storage-usage.md) | Upload, list, download, versioning. |
| [Caching](caching.md) | Memory / Redis / layered caches; read-through DB wrapper. |
| [Text Normalization](text-normalization.md) | Unicode → ASCII normalization for query stability. |

## Observability and Operations

| Document | What's in it |
|---|---|
| [Observability](observability.md) | **NEW** Structured DB op logs, `MetricsRecorder`, slow-query threshold, OTEL adapter. |
| [Logging Service](logging-service.md) | Persistent application logging. |
| [Custom Log Levels](custom-log-levels.md) | Adding domain levels (`AUDIT`, `SECURITY`, …). |
| [Benchmarks](benchmarks.md) | **NEW** Regression-detection bench suite. |
| [Serverless Mode](serverless-mode.md) | **NEW** Detection precedence, mode-dependent defaults, LWA env. |
| [Scheduler](scheduler.md) | In-process scheduler and decorators. |
| [Webhook Architecture](webhook-architecture.md) | Webhook routing, signature verification. |
| [Webhooks Quickstart](webhooks-quickstart.md) | Common webhook patterns. |
| [Troubleshooting](troubleshooting.md) | Symptoms → root causes for common issues. |

## Architecture and Conventions

| Document | What's in it |
|---|---|
| [Architectural Decisions](architectural-decisions.md) | ADR-style design rationale. |
| [Design Decisions](design-decisions.md) | Philosophy and tradeoffs. |
| [Module Responsibility Matrix](module-responsibility-matrix.md) | Which package owns which concern. |
| [Import Patterns](import-patterns.md) | Stable vs internal imports. |
| [Stability](stability.md) | **NEW** Public / internal / experimental tiers + deprecation policy. |
| [Optimization](optimization.md) | Performance tuning: `neighborhood`, walker prefetch, Postgres paths, fast deserialize. |

## Configuration

| Document | What's in it |
|---|---|
| [Environment Configuration](environment-configuration.md) | `JVSPATIAL_*` allowlist behavior and merge order. |
| [Environment Keys Reference](environment-keys-reference.md) | Canonical inventory of every valid env key. |

## Contributing

| Document | What's in it |
|---|---|
| [Contributing](contributing.md) | Dev loop, conventions, label glossary. |
| [Testing Guide](testing-guide.md) | Async test patterns, fixtures, auth-test isolation. |
| [License](license.md) | MIT license reference. |

---

## Quick Reference

### Common Tasks

| Task | Start here |
|---|---|
| Create your first node + endpoint | [Quick Start Guide](quick-start-guide.md) |
| Switch from JSON to MongoDB | [Graph Context](graph-context.md) |
| Add authentication | [Auth Quickstart](auth-quickstart.md) |
| Implement a custom database backend | [Custom Database Guide](custom-database-guide.md) |
| Deploy to AWS Lambda | [Serverless Mode](serverless-mode.md), [Production Deployment](production-deployment.md) |
| Build a walker | [Graph Traversal](graph-traversal.md), [Walker Events](walker-reporting-events.md) |
| Surface metrics | [Observability](observability.md) |
| Verify SLA / catch regressions | [Benchmarks](benchmarks.md) |
| Audit security posture | [Security Review](security-review.md), [Security Operational Notes](security-operational-notes.md) |

### Authoritative Sources

When documents disagree, this is the order of trust:

1. Source code (cited in [SPEC.md](../../SPEC.md))
2. [SPEC.md](../../SPEC.md) — contract
3. [PRD.md](../../PRD.md) — product context
4. [docs/md/](.) — how-to documentation
5. [LLM-CODING-GUIDE.md](../../LLM-CODING-GUIDE.md) — legacy code-pattern cookbook (no longer authoritative on contracts)

If you find a doc in this directory that contradicts SPEC, the doc is wrong — open an issue.
