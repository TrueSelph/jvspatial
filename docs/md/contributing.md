# Contributing

## Development Setup
```bash
git clone https://github.com/TrueSelph/jvspatial
cd jvspatial
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e '.[dev]'  # Note: quotes needed for zsh
```

## Code Style
- Black formatting
- isort imports
- flake8 linting
- mypy type checking

```bash
# Format code
black jvspatial/
isort jvspatial/

# Run checks
flake8 jvspatial/
mypy jvspatial/
```

## Testing
```bash
# Run all tests
pytest

# Test with coverage
pytest --cov=jvspatial --cov-report=html
```

## Contribution Guidelines

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/amazing-feature`
3. **Write tests** for your changes
4. **Ensure tests pass**: `python -m pytest`
5. **Update documentation** if needed
6. **Commit** your changes: `git commit -m 'Add amazing feature'`
7. **Push** to your fork: `git push origin feature/amazing-feature`
8. **Create** a Pull Request

## Code Review Process

- All PRs require 2 maintainer approvals
- CI tests must pass
- Documentation updates must match code changes

## Reporting Issues

Please include:
- jvspatial version
- Reproduction steps
- Expected vs actual behavior
- Relevant error logs

## See Also

- [Examples](examples.md) - Working examples for reference
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
- [Entity Reference](entity-reference.md) - Complete API reference
- [License](license.md) - License information

---

**[← Back to README](../../README.md)** | **[License →](license.md)**
