# PyPI Publishing Workflow Summary

## Overview

The `publish.yml` workflow automatically creates git tags and publishes to PyPI when source code changes are merged into the `main` branch.

## Trigger Conditions

### ✅ Triggers When:
- Code is **pushed to `main` branch** (includes PR merges)
- **AND** source code files have changed:
  - Python files in `jvspatial/` directory
  - `setup.py`
  - `pyproject.toml`
  - `requirements*.txt` files
  - `jvspatial/version.py`

### ❌ Does NOT Trigger When:
- Only documentation files changed (`.md`, `docs/`)
- Only example code changed (`examples/`)
- Only test files changed (`tests/`)
- Only GitHub config changed (`.github/`)
- Only build artifacts or cache files changed

## Workflow Steps

1. **Checkout Repository**: Fetches full history and all tags
2. **Set up Python**: Uses Python 3.11
3. **Check for Source Code Changes**:
   - Verifies actual source code changed (not just docs)
   - Counts Python files, config files, and version changes
   - Skips publish if no source code changes detected
4. **Read Version**: Extracts version from `jvspatial/version.py`
5. **Validate Version**: Ensures format is X.Y.Z (semantic versioning)
6. **Check Tag Exists**: Verifies if git tag already exists
7. **Create Tag**: Creates and pushes `v{version}` tag if it doesn't exist
8. **Build Package**: Creates wheel and source distribution
9. **Validate Package**: Runs `twine check` to verify package
10. **Publish to PyPI**: Uploads using trusted publishing
11. **Save Artifacts**: Saves build artifacts on failure (for debugging)

## Key Features

- ✅ **Automatic Tagging**: Creates git tags automatically
- ✅ **Source Code Detection**: Only publishes when code actually changes
- ✅ **Idempotent**: Safe to re-run (won't create duplicate tags)
- ✅ **Validated**: Checks version format and package validity
- ✅ **Secure**: Uses PyPI trusted publishing (no tokens needed)

## Example Workflow

```bash
# 1. Update version
echo '__version__ = "0.0.2"' > jvspatial/version.py

# 2. Make code changes
# ... edit jvspatial/core/context.py ...

# 3. Commit and push
git add jvspatial/version.py jvspatial/core/context.py
git commit -m "Add feature X - version 0.0.2"
git push origin main

# 4. GitHub Actions automatically:
#    - Detects source code changes ✅
#    - Reads version: 0.0.2
#    - Creates tag: v0.0.2
#    - Builds package
#    - Publishes to PyPI
```

## Verification

The workflow includes multiple safety checks:
- Source code change detection (prevents publishing on docs-only changes)
- Version format validation (ensures semantic versioning)
- Tag existence check (prevents duplicate tags)
- Package validation (ensures package is valid before publishing)

