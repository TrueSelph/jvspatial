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
pytest --cov=jvspatial --cov-fail-under=60
# The configured mypy pre-commit hook is part of pre-commit above.
```

Both commands must be green. The standalone `mypy jvspatial/` invocation has pre-existing diagnostics outside the configured hook scope; track that debt separately. CI will re-run the gates on the PR — local runs
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

### 8. Verify the GitHub release

The stable publish workflow creates a GitHub release with generated notes when
it creates a new version tag. Verify that the release references the expected
commit and that package upload succeeds. A GitHub release entry alone does not
prove successful PyPI publication; inspect the publish job and package page.

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

Release candidates publish to TestPyPI through
`.github/workflows/publish-testpypi.yml`. This lane is separate from
`publish.yml`, which remains responsible for stable releases to PyPI.

### Publish a candidate

1. Prepare a candidate branch with the normal quality gates green and
   the candidate changes recorded in `CHANGELOG.md`.
2. Set `jvspatial/version.py` to a PEP 440 candidate version such as
   `0.2.0rc1` (or `0.2.0rc2` for the next iteration).
3. Commit the candidate and create a matching annotated tag, then push
   the tag:

   ```bash
   git tag -a v0.2.0rc1 -m "jvspatial 0.2.0rc1"
   git push origin v0.2.0rc1
   ```

4. The tag starts the candidate workflow. It verifies that the tag and
   `version.py` agree, builds and validates the wheel and sdist, then
   publishes them to TestPyPI. Check the Actions run and the TestPyPI
   project page before asking consumers to try the candidate.

The workflow accepts only tags matching `vX.Y.ZrcN`. Do not merge a
candidate version into `main`: the stable PyPI workflow accepts only
`X.Y.Z`. For the final release, prepare the normal release PR with the
stable version (for example `0.2.0`) and follow the checklist above.

TestPyPI must have a Trusted Publisher configured for repository
`TrueSelph/jvspatial` and workflow `publish-testpypi.yml` (with no
environment unless the publisher is configured to require one). No
PyPI token secret is needed. Existing TestPyPI versions cannot be
overwritten; increment the `rcN` suffix for every candidate rebuild.

## See also

- [`.github/workflows/publish.yml`](.github/workflows/publish.yml) — actual publication automation
- [`.github/workflows/publish-testpypi.yml`](.github/workflows/publish-testpypi.yml) — release-candidate publication automation
- [`.github/workflows/VERSIONING.md`](.github/workflows/VERSIONING.md) — workflow's own notes
- [CHANGELOG.md](CHANGELOG.md) — the artifact this whole flow produces
