# GitHub Actions Workflows

## PyPI Publishing Workflow

The `publish.yml` workflow automatically publishes the `jvspatial` package to PyPI when code is merged to the `main` branch.

### Setup Instructions

#### Option 1: Trusted Publishing (Recommended - More Secure)

Trusted publishing is the modern, secure way to publish to PyPI without managing API tokens.

1. **Enable Trusted Publishing on PyPI:**
   - Go to https://pypi.org/manage/account/
   - Navigate to the "API tokens" section
   - Click "Add a new pending publisher"
   - Fill in the form:
     - **PyPI project name:** `jvspatial`
     - **Owner:** `TrueSelph` (or your GitHub username/org)
     - **Repository name:** `jvspatial`
     - **Workflow filename:** `publish.yml`
     - **Environment name:** (leave empty or use `production`)
     - **Specific branch:** `main`
   - Click "Add"

2. **Verify the workflow is configured correctly:**
   - The workflow file should have `id-token: write` permission (already set)
   - The workflow should use `pypa/gh-action-pypi-publish@release/v1` (already configured)

3. **Test the workflow:**
   - Merge a change to the `main` branch
   - The workflow will automatically trigger and publish to PyPI

#### Option 2: API Token (Alternative)

If you prefer to use an API token instead:

1. **Create a PyPI API Token:**
   - Go to https://pypi.org/manage/account/token/
   - Click "Add API token"
   - Give it a name (e.g., "GitHub Actions")
   - Set scope to "Entire account" or limit to the `jvspatial` project
   - Copy the token (you won't see it again!)

2. **Add the token as a GitHub Secret:**
   - Go to your repository on GitHub
   - Navigate to Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `PYPI_API_TOKEN`
   - Value: Paste your PyPI API token
   - Click "Add secret"

3. **Update the workflow file:**
   - Edit `.github/workflows/publish.yml`
   - In the "Publish to PyPI" step, uncomment:
     ```yaml
     password: ${{ secrets.PYPI_API_TOKEN }}
     username: __token__
     ```
   - Comment out or remove the trusted publishing section

### Workflow Behavior

- **Triggers:** Automatically runs on pushes to the `main` branch (including PR merges)
- **Source Code Detection:** Only triggers when source code files change:
  - Python files in `jvspatial/` directory
  - `setup.py`, `pyproject.toml`, `requirements*.txt`
  - `jvspatial/version.py` (version changes)
- **Ignores:** Documentation, examples, tests, and build artifacts
- **Tag Creation:** Automatically creates git tag if it doesn't exist
- **Builds:** Creates both wheel and source distribution
- **Validates:** Runs `twine check` to validate the package before publishing
- **Publishes:** Uploads to PyPI automatically
- **Artifacts:** Saves build artifacts if the workflow fails (for debugging)

### Version Management

The workflow uses the version specified in `jvspatial/version.py`. To release a new version:

1. Update the version in `jvspatial/version.py`
2. Commit and push to `main` (or merge PR to main)
3. The workflow will automatically:
   - Read the version from `version.py`
   - Create git tag if it doesn't exist
   - Build and publish to PyPI

### Troubleshooting

- **Workflow doesn't trigger:** Check that you're pushing to the `main` branch (not `master`)
- **Publishing fails:** Check the workflow logs for specific error messages
- **Version conflicts:** Ensure the version in `pyproject.toml` is higher than the current PyPI version
- **Trusted publishing not working:** Verify the publisher configuration on PyPI matches your repository exactly

