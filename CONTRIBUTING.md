# Contributing to jvspatial

Thanks for your interest in contributing. jvspatial is an async-first,
graph-based persistence library and we're looking for contributors who
want to help make it the kind of library you'd reach for first when
building object-spatial applications.

This file lives at the repo root so GitHub surfaces it on issue and
pull-request pages. The narrative dev guide lives at
[`docs/md/contributing.md`](docs/md/contributing.md) — read both.

## Ground rules

- Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Security issues do **not** go in public issues. See
  [SECURITY.md](SECURITY.md).
- Breaking changes need a justification in the PR description and an
  entry under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) marked
  `**BREAKING**`.

## Quickest possible loop

```bash
# 1. clone + venv
git clone https://github.com/TrueSelph/jvspatial
cd jvspatial
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# 2. install with dev + test extras
pip install -e '.[dev,test]'

# 3. install pre-commit hooks (one-time)
pre-commit install

# 4. run the tests
pytest -q

# 5. run the full quality bar locally before opening a PR
pre-commit run --all-files
pytest --cov=jvspatial --cov-report=term-missing
```

If `pre-commit run` and `pytest` are both green, your PR is in good
shape.

## What we look for in a PR

In rough priority order:

1. **A failing test that reproduces the bug** (for bug fixes), or **a
   passing test that exercises the new behavior** (for features).
   Tests come first — implementations follow.
2. **Smallest reasonable diff.** A 200-line PR that does one thing
   well lands faster than a 2000-line PR that does five.
3. **Backwards-compatible by default.** If a change is breaking, say
   so loudly in the PR title (`BREAKING:` prefix) and the changelog.
4. **Documentation updated alongside code.** Docstrings, the relevant
   page in `docs/md/`, and `CHANGELOG.md` under `[Unreleased]`.
5. **No new unbounded resources.** Caches need a max size, work
   queues need a max depth, retries need a backoff cap. The library
   runs in serverless environments where unbounded resources fail
   silently.

## Architecture invariants we enforce in review

- **Async-first.** Public APIs are `async def`. Sync compatibility
  shims are allowed but must not block the event loop.
- **Serverless-safe.** No background tasks, sweepers, or watchdogs
  that assume a long-lived process. Anything that relies on
  long-lived state must check `is_serverless_mode()` and degrade
  cleanly. See `jvspatial/runtime/serverless.py`.
- **IO honesty.** Persistence calls should not silently fail or
  silently no-op. If an adapter doesn't support an operation, raise
  `NotImplementedError` and expose a capability flag (e.g.
  `Database.supports_transactions`). See
  [`docs/md/stability.md`](docs/md/stability.md) for the broader
  stability contract.
- **Single source of truth for config.** All server settings flow
  through `ServerConfig`. Don't read environment variables ad-hoc
  from inside library code — go through the config object.

## Branch and commit conventions

- **Branch name:** `<area>/<short-description>`
  e.g. `db/sqlite-pushdown`, `api/rate-limit-fix`,
  `docs/contributing-cleanup`.
- **Commit messages:** imperative mood, present tense, no trailing
  period. The first line is ≤ 72 chars; longer rationale goes in the
  body separated by a blank line.

  ```
  Add SQLite filter pushdown for $in/$nin

  json_extract() WHERE clauses for the operator subset listed in
  _sqlite_translate.py. Falls back to the legacy in-Python filter
  for $regex / $elemMatch / etc. so behavior is preserved.

  Closes #123.
  ```

- **PR title:** the same imperative summary. Use `BREAKING:` as a
  prefix when the change is not backwards compatible.

## Issue triage labels

We use these labels when triaging:

- `good first issue` — small, well-scoped, doesn't require deep
  context. Mentored if needed.
- `help wanted` — we'd love a contributor on this; the path forward
  is reasonably clear.
- `needs design` — the right answer isn't obvious; we need a design
  proposal in the issue before code is written.
- `breaking` — fix requires a breaking change. Will land in the next
  minor (pre-1.0).
- `serverless` — touches serverless behavior; needs Lambda-mode
  testing.
- `io` / `db` / `api` / `core` / `storage` — area tags so you can
  filter to your area of interest.

## Running the full test matrix locally

```bash
# fast loop: just unit tests (benchmarks are excluded by default)
pytest -q

# everything, with coverage gate
pytest --cov=jvspatial --cov-fail-under=50

# a single file or single test
pytest tests/db/test_sqlite_pushdown.py -v
pytest tests/db/test_sqlite_pushdown.py::TestCountPushdown::test_filtered_count_pushdown -v

# type checking (matches CI)
mypy jvspatial/

# style (matches pre-commit)
black --check jvspatial/ tests/
isort --check-only jvspatial/ tests/
flake8 jvspatial/ tests/

# performance benchmarks (only run when asked; not part of -q above)
pytest tests/benchmarks --benchmark-only
```

For details on the benchmark suite (what's in it, what CI does with
it, how to add new benches) see
[`docs/md/benchmarks.md`](docs/md/benchmarks.md).

## When in doubt

Open a draft PR with a clear title and a description of what you're
trying to accomplish. We'd rather give early feedback on a
work-in-progress than receive a finished 2000-line PR going in the
wrong direction.

## See also

- [docs/md/contributing.md](docs/md/contributing.md) — narrative dev guide
- [docs/md/stability.md](docs/md/stability.md) — public vs. internal API tiers
- [docs/md/architectural-decisions.md](docs/md/architectural-decisions.md)
- [RELEASING.md](RELEASING.md) — release flow for maintainers
