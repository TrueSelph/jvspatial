# AGENTS.md — Multi-agent compatibility shim

This file exists so AI coding assistants that follow the `AGENTS.md` convention (Codex, Cursor, Aider, Continue, OpenHands, and others) find the same guidance as Claude Code.

**The canonical agent guide is [CLAUDE.md](CLAUDE.md).** Treat it as authoritative.

This file does not duplicate that content; agents that read this file should read [CLAUDE.md](CLAUDE.md) instead.

---

## Quick orientation

If you cannot follow the link to `CLAUDE.md`, here is the minimum:

- **What this repo is**: `jvspatial`, an async-first Python library for graph-based persistence with FastAPI integration. See [README.md](README.md) and [PRD.md](PRD.md).
- **Where the contract lives**: [SPEC.md](SPEC.md). Every claim cites a `file:line`. If your edit changes a contract, update SPEC in the same commit.
- **How docs are organized**: [docs/md/README.md](docs/md/README.md) is the index. PRD / SPEC / ROADMAP / CLAUDE live at the repo root.
- **Forward direction**: [ROADMAP.md](ROADMAP.md) — current focus areas, known gaps, out-of-scope.
- **What changed recently**: [CHANGELOG.md](CHANGELOG.md).

---

## Non-negotiable invariants (summary)

Full list in [CLAUDE.md § Non-negotiable invariants](CLAUDE.md#non-negotiable-invariants). Top items:

1. Async-only I/O. No sync wrappers.
2. `hmac.compare_digest` for every secret comparison.
3. `__entity_name__` honors per-subclass override; do not assemble IDs from `cls.__name__`.
4. Serverless detection precedence: explicit config → current Server config → `SERVERLESS_MODE` env → auto-detect.
5. Stability tiers in [docs/md/stability.md](docs/md/stability.md) are binding. Public names live in `jvspatial.__all__`; underscore modules are internal.
6. CORS/CSP/docs defaults fail closed; do not weaken without a security review.

---

## Run the dev loop

```bash
pip install -e '.[dev,test]'
pre-commit install
pytest -q
pre-commit run --all-files
```

Tests are async (`pytest-asyncio` auto mode). Benchmarks are skipped by default — run with `pytest tests/benchmarks --benchmark-only`.

---

## Editor / agent-tool specific notes

This section is the only place where agent-tool-specific guidance lives. Keep it short; cross-link to CLAUDE.md for everything else.

- **Cursor / Continue**: `.cursor/` directory is gitignored except for committed rules. There are no committed `.cursorrules`; this file plus CLAUDE.md is the full agent contract.
- **Aider**: `--read CLAUDE.md` to load the canonical guide on session start.
- **Codex / OpenHands**: this file is loaded as agent instructions; read CLAUDE.md for full details.

Any agent-specific quirk worth recording goes here, with a one-line rationale. If a quirk grows beyond a line, promote it into CLAUDE.md and reference back.
