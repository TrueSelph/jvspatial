# jvspatial Examples

> **🎯 Standard API Examples**: For building custom jvspatial APIs, start with:
> - **[Authenticated API Example](api/authenticated_endpoints_example.py)** - Complete CRUD with authentication
> - **[Unauthenticated API Example](api/unauthenticated_endpoints_example.py)** - Public read-only API
>
> See [API Examples README](api/README.md) for details.

# jvspatial Examples

This directory contains examples demonstrating various features of jvspatial.

## Example Categories

### 🔰 Error Handling Examples
Robust error handling patterns and best practices:

- `error_handling/basic_error_handling.py` - Fundamental error patterns
- `error_handling/database_error_handling.py` - Database error handling
- `error_handling/walker_error_handling.py` - Walker error handling

### ✨ Updated Examples (New Walker Patterns)
These examples have been updated to use the report() pattern and current import structure:

- `travel_graph.py` - Travel planning with graph traversal
- `graphcontext_demo.py` - Graph context management
- `agent_graph.py` - Hierarchical agent system
- `multi_target_hooks_demo.py` - Multiple target hook handling

### 📊 Core Examples
- `walker_traversal_demo.py` - Basic walker traversals
- `enhanced_nodes_filtering.py` - Advanced node filtering
- `query_interface_example.py` - Query interface usage
- `object_pagination_demo.py` - Object pagination
- `semantic_filtering.py` - Semantic-based filtering
- `unified_query_interface_example.py` - Unified query interface
- `custom_database_example.py` - Custom database integration
- `database_switching_example.py` - Dynamic database switching
- `database/multi_database_example.py` - **Multi-database support** - Managing multiple databases with prime database for core persistence
- `walker_events_demo.py` - Walker event handling
- `walker_reporting_demo.py` - Walker reporting functionality

### 🌐 Server Examples
These examples demonstrate server functionality and validate server startup:

- `comprehensive_server_example.py` - Complete server implementation
- `server_example.py` - Basic server setup
- `server_demo.py` - Server demonstrations
- `fastapi_server.py` - FastAPI integration
- `dynamic_server_demo.py` - Dynamic server configuration
- `dynamic_endpoint_removal.py` - Dynamic endpoint management
- `endpoint_decorator_demo.py` - Endpoint decorator usage
- `endpoint_respond_demo.py` - Endpoint response handling
- `exception_handling_demo.py` - Error handling
- `webhook_examples.py` - Webhook integration

### ⏱️ Long Running Examples
These examples run indefinitely (servers, schedulers):

- `auth/auth_demo.py` - Authentication demo (runs continuously)
- `scheduler/scheduler_example.py` - Scheduler integration (runs continuously)

## Getting Started

1. Install jvspatial with all features:
```bash
pip install jvspatial[all]
```

2. Set up environment (if needed):
```bash
cp .env.example .env
# Edit .env with your settings
```

3. Run any example:
```bash
python examples/database/custom_database_example.py
python examples/walkers/walker_traversal_demo.py
```

## Testing

Run all example tests with:

```bash
python examples/test_examples.py
```

This will validate all examples and provide a summary of:
- ✅ Passed examples
- ❌ Failed examples
- ⏭️ Skipped examples (long-running or requiring updates)
