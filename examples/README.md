# jvspatial Examples

This directory contains examples demonstrating various features of jvspatial.

## Directory Structure

- [api/](api/) - API server and endpoint examples
- [auth/](auth/) - Authentication and authorization examples
- [core/](core/) - Core features and basic usage
- [database/](database/) - Database backend and ORM examples
- [integrations/](integrations/) - External integrations (webhooks, scheduler)
- [storage/](storage/) - File storage examples
- [walkers/](walkers/) - Walker and traversal examples

## Getting Started

Each subdirectory contains a README with specific information about the examples in that category.

1. Make sure you have jvspatial installed:
```bash
pip install jvspatial
```

2. Copy .env.example to .env and configure:
```bash
cp .env.example .env
# Edit .env with your settings
```

3. Run any example:
```bash
python -m examples.api.server_example
```

## Example Categories

### API Examples
Complete API server implementations showing FastAPI integration, endpoint handling, error management, and dynamic configuration.

### Auth Examples
Authentication and authorization examples including JWT tokens, API keys, and permission-based access control.

### Core Examples
Basic usage examples showing entity modeling, graph operations, and spatial functionality.

### Database Examples
Database backend customization, ORM features, and query interface examples.

### Integration Examples
External service integration examples including webhooks and scheduled tasks.

### Storage Examples
File storage examples showing local and cloud (S3) storage integration.

### Walker Examples
Graph traversal examples showing Walker patterns, event handling, and data collection.

## Testing

The examples include tests in test_examples.py. Run them with:

```bash
pytest test_examples.py
```

This directory contains working examples demonstrating different aspects of the jvspatial library.

## Directory Structure

- `core/` - Core functionality examples (Nodes, Edges, Walkers)
- `api/` - FastAPI integration and endpoint examples
- `storage/` - File storage and proxy functionality
- `auth/` - Authentication and security features

## Running Examples

Each example can be run directly with Python after installing jvspatial:

```bash
# Install jvspatial with all features
pip install jvspatial[all]

# Run a specific example
python examples/core/cities.py
```

## Environment Setup

Some examples require environment variables to be set. You can use the `.env` file in each directory as a template:

```bash
# Copy the example env file
cp examples/api/.env.example examples/api/.env

# Edit with your settings
vim examples/api/.env
```