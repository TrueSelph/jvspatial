# Releasing jvspatial

This is the maintainer-only release procedure. Contributors don't
need to read this — see [CONTRIBUTING.md](CONTRIBUTING.md) instead.

## How releases happen here

Releases are **driven by `jvspatial/version.py`**, not by manually
pushing a tag. The publish workflow (`.github/workflows/publish.yml`)
runs on every push to `main` and:

1. Reads `__version__` from `jvspatial/version.py`.
2. Decides whether to publish based on whether the diff includes
   source changes, config changes, or a version bump.
3. If the corresponding `vX.Y.Z` tag does not exist yet, creates and
   pushes it.
4. Builds a wheel + sdist with `python -m build`.
5. Validates with `twine check`.
6. Uploads to PyPI via Trusted Publishing (OIDC) — no API token secret required.

This means **a release is just a PR that bumps `version.py` and
edits `CHANGELOG.md`**. Once it merges, PyPI publication is
automatic.

## Versioning policy

We follow [Semantic Versioning](https://semver.org/). Pre-1.0:

- **Patch** (`0.0.X` → `0.0.X+1`): bug fixes, internal refactors,
  no behavior change for adopters.
- **Minor** (`0.X.0` → `0.X+1.0`): new features, *and* the
  acceptable home for breaking changes while we're pre-1.0.
  Breaking changes must be marked clearly in the changelog.
- **Major** (`0.X.0` → `1.0.0`): the 1.0 line. After 1.0, breaking
  changes only land in major bumps.

We treat each pre-1.0 minor as a breaking-change boundary. If a
security fix needs a breaking change, it ships in the next minor.

## The release checklist

Run through these steps in a single PR. Don't push directly to
`main`; the publish workflow runs on merge.

### 1. Confirm the diff is releasable

```bash
git fetch origin
git log --oneline origin/main..HEAD
```

Any item in that list should be either (a) in the changelog under
`## [Unreleased]` or (b) explicitly excluded with a justification
(internal-only refactor, comment fix, etc.).

### 2. Run the full quality bar

```bash
pre-commit run --all-files
pytest --cov=jvspatial --cov-fail-under=50
mypy jvspatial/
```

All three must be green. CI will re-run them on the PR — local runs
just save a round trip.

### 3. Pick the new version number

Decide based on the cumulative diff since the last release:

- Any `**BREAKING**` entries in `## [Unreleased]` → minor bump.
- Any `### Added` entries → minor bump (or patch if you've decided
  the additions are too small to warrant a minor; document the
  reasoning in the PR).
- Only `### Fixed` / `### Security` (non-breaking) → patch bump.

### 4. Update `jvspatial/version.py`

```python
__version__ = "0.X.Y"
```

That's the whole file change. The workflow reads it via regex.

### 5. Update `CHANGELOG.md`

Move the `## [Unreleased]` block contents under a new dated heading:

```markdown
## [Unreleased]

## [0.X.Y] - YYYY-MM-DD

### Security

- ...

### Added

- ...

### Changed

- ...

### Fixed

- ...
```

Always leave a fresh empty `## [Unreleased]` block at the top so
future PRs have somewhere to land their notes.

### 6. Open the release PR

- Title: `Release 0.X.Y`.
- Description: paste the new changelog block as the PR body so
  reviewers see the release notes in one place.
- Label: `release`.
- Reviewer: at least one other maintainer.

### 7. Merge and watch

After merge, the publish workflow will:

1. Tag `v0.X.Y` automatically (from `version.py`).
2. Build and upload to PyPI.

Confirm by checking:

- <https://pypi.org/project/jvspatial/> shows the new version.
- The Actions tab shows the workflow as ✅.
- `git fetch --tags` locally shows `v0.X.Y`.

### 8. Cut a GitHub release

After the PyPI upload succeeds, cut a GitHub release from the
auto-created tag. Paste the changelog block into the release body.
This is currently a manual step — automating it is on the to-do.

### 9. If something goes wrong

- **Workflow failed before PyPI upload:** fix forward in a new PR
  bumping the patch version. Don't try to re-run a failed workflow
  with the same version — PyPI doesn't allow re-uploading the same
  filename.
- **PyPI upload succeeded but the package is broken:** *yank* the
  release on PyPI (don't delete) and ship a fixed patch version.
  Yanking keeps anyone who pinned the broken version building, but
  hides it from unpinned `pip install jvspatial`.

## Hotfix releases

For high-severity bugs against a released version where a normal
forward fix isn't acceptable:

1. Branch off the relevant tag: `git checkout -b hotfix/0.X.Y+1 v0.X.Y`.
2. Apply the minimal fix.
3. Bump the patch version and changelog.
4. Open a PR targeting `main` (not the release branch) — once
   merged, the workflow handles publication.

We don't currently maintain release branches per minor; pre-1.0,
adopters are expected to track the latest minor.

## Pre-release versions (alpha / beta / rc)

The current workflow does not publish pre-release versions. If we
need one (e.g. for a 1.0 candidate), the workflow regex in
`publish.yml` step `Read version from version.py` enforces the
`MAJOR.MINOR.PATCH` form and rejects suffixes like `0.1.0a1`. We'll
update the regex and the validation when the first pre-release is
needed.

## See also

- [`.github/workflows/publish.yml`](.github/workflows/publish.yml) — actual publication automation
- [`.github/workflows/VERSIONING.md`](.github/workflows/VERSIONING.md) — workflow's own notes
- [CHANGELOG.md](CHANGELOG.md) — the artifact this whole flow produces
