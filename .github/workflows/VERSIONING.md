# Version Management Guide

This project uses a **Python file-based version management system** where the version is specified in `jvspatial/version.py` and the GitHub Actions workflow automatically creates git tags and publishes to PyPI.

## How It Works

1. **Version Source**: Version is specified in `jvspatial/version.py` as `__version__`
2. **Automatic Tagging**: When you push to `main`, the workflow:
   - Reads the version from `jvspatial/version.py`
   - Checks if a git tag for that version already exists
   - Creates and pushes the tag if it doesn't exist
   - Builds and publishes to PyPI
3. **Single Source of Truth**: The version in `jvspatial/version.py` is used everywhere

## Releasing a New Version

### Step 1: Update the Version File

Edit `jvspatial/version.py`:

```python
__version__ = "0.2.1"  # Update this line
```

### Step 2: Commit and Push to Main

```bash
git add jvspatial/version.py
git commit -m "Bump version to 0.2.1"
git push origin main
```

### Step 3: GitHub Actions Will Automatically

1. Read the version from `jvspatial/version.py`
2. Check if tag `v0.2.1` exists
3. Create the tag if it doesn't exist
4. Build the package with that version
5. Publish to PyPI

## Version Number Format

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0): Breaking changes
- **MINOR** (0.1.0): New features, backward compatible
- **PATCH** (0.0.1): Bug fixes, backward compatible

### Examples

```python
# Initial release
__version__ = "0.1.0"

# Bug fix
__version__ = "0.1.1"

# New feature
__version__ = "0.2.0"

# Breaking change
__version__ = "1.0.0"
```

## Workflow Behavior

### Trigger Conditions

The workflow triggers when:
- Code is pushed to the `main` branch (including PR merges)
- **AND** source code files have changed (not just documentation)

**Source code changes that trigger publishing:**
- Python files in `jvspatial/` directory
- `setup.py`, `pyproject.toml`, `requirements*.txt`
- `jvspatial/version.py` (version changes)

**Files that do NOT trigger publishing:**
- Documentation files (`.md`, `docs/`)
- Example code (`examples/`)
- Test files (`tests/`)
- Build artifacts, cache files, etc.

### Publishing Process

When triggered, the workflow:

1. **Checks for source code changes**: Verifies actual code changed (not just docs)
2. **Reads version** from `jvspatial/version.py`
3. **Checks for existing tag**: If tag `v{version}` already exists, skips tag creation
4. **Creates tag**: If tag doesn't exist, creates `v{version}` tag automatically
5. **Builds package**: Uses the version from `version.py`
6. **Validates package**: Runs `twine check` to ensure package is valid
7. **Publishes to PyPI**: Automatically uploads the package

### Tag Creation

The workflow will:
- Create an annotated tag: `v0.2.1`
- Tag message: "Release version 0.2.1"
- Push the tag to the repository
- Only create if the tag doesn't already exist (idempotent)

## Checking Current Version

### In Code

```python
from jvspatial import __version__
print(__version__)  # e.g., "0.2.0"
```

### From File

```bash
grep "__version__" jvspatial/version.py
```

### From Git Tags

```bash
git tag -l "v*"           # List all version tags
git describe --tags      # Latest tag
```

## Best Practices

1. **Update version before merging**: Update `jvspatial/version.py` in your PR
2. **Use semantic versioning**: Follow MAJOR.MINOR.PATCH format
3. **Commit version separately**: Make version bump a clear commit message
4. **Test before releasing**: Ensure tests pass before pushing version update

## Troubleshooting

### Version not updating

- Check that `jvspatial/version.py` was committed and pushed
- Verify the version format is correct (e.g., `"0.2.0"` not `0.2.0`)
- Check workflow logs for version extraction

### Tag already exists

- If the tag exists, the workflow will skip tag creation
- This is normal if you're re-running the workflow
- The package will still be built and published with that version

### Package not publishing

- Check workflow logs for errors
- Verify PyPI trusted publishing is configured
- Ensure the version in `version.py` is higher than the current PyPI version

### Workflow not triggering

- Ensure you're pushing to the `main` branch
- Check that `jvspatial/version.py` is not in `paths-ignore`
- Verify the workflow file is in `.github/workflows/`

## Example Release Workflow

```bash
# 1. Update version
echo '__version__ = "0.2.1"' > jvspatial/version.py

# 2. Commit
git add jvspatial/version.py
git commit -m "Release version 0.2.1"

# 3. Push to main
git push origin main

# 4. GitHub Actions will:
#    - Read version: 0.2.1
#    - Create tag: v0.2.1
#    - Build package
#    - Publish to PyPI
```

## Advantages of This Approach

✅ **Simple**: Just update one Python file
✅ **Automatic**: No manual tag creation needed
✅ **Idempotent**: Safe to re-run (won't create duplicate tags)
✅ **Clear**: Version is visible in the codebase
✅ **Integrated**: Works seamlessly with CI/CD
