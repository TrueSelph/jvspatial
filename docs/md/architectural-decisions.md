# Architectural Decision Records (ADR)

**Project**: jvspatial
**Version**: 0.0.1
**Date**: 2025-10-20

This document records key architectural decisions made during the development and refactoring of the jvspatial library.

---

## 📋 **Table of Contents**

1. [ADR-001: Module Organization](#adr-001-module-organization)
2. [ADR-002: Decorator Separation](#adr-002-decorator-separation)
3. [ADR-003: Common → Utils Rename](#adr-003-common--utils-rename)
4. [ADR-004: Response Consolidation](#adr-004-response-consolidation)
5. [ADR-005: Storage Interfaces](#adr-005-storage-interfaces)
6. [ADR-006: Core Structure](#adr-006-core-structure)
7. [ADR-007: Type System](#adr-007-type-system)
8. [ADR-008: Context Management](#adr-008-context-management)

---

## ADR-001: Module Organization

**Date**: 2025-10-15
**Status**: ✅ Accepted
**Deciders**: Development Team

### **Context**

The library had grown organically with some modules having unclear boundaries and overlapping responsibilities. We needed a clear, maintainable structure.

### **Decision**

Organize the library into six top-level modules with distinct responsibilities:

1. **`core/`** - Graph entities and traversal
2. **`api/`** - REST API and server
3. **`db/`** - Database abstraction
4. **`cache/`** - Caching backends
5. **`storage/`** - File storage
6. **`utils/`** - Shared utilities

### **Rationale**

- **Separation of Concerns**: Each module has a single, clear purpose
- **Scalability**: Easy to find and extend functionality
- **Testability**: Modules can be tested independently
- **Documentation**: Clear module boundaries improve documentation

### **Consequences**

**Positive**:
- Clear module responsibilities
- Easier onboarding for new developers
- Better test isolation
- Improved documentation structure

**Negative**:
- Large refactoring effort
- Import path updates required

### **Alternatives Considered**

1. **Monolithic structure**: Rejected - poor scalability
2. **Microservices-style split**: Rejected - too complex for a library
3. **Domain-driven design**: Partially adopted - some concepts applied

---

## ADR-002: Decorator Separation

**Date**: 2025-10-18
**Status**: ✅ Accepted
**Deciders**: Development Team

### **Context**

There were two types of decorators:
1. Route-level decorators (`@endpoint`, `@auth_endpoint`)
2. Field-level decorators (`endpoint_field`)

Both were initially mixed, causing confusion about when to use each.

### **Decision**

Separate decorators into distinct submodules:
- `api/decorators/route.py` - Route-level decorators
- `api/decorators/field.py` - Field-level decorators
- `api/decorators/route_config.py` - Advanced route configuration

Re-export all from `api/decorators/__init__.py` for convenient access.

### **Rationale**

- **Clarity**: Clear distinction between decorator types
- **Discoverability**: Easy to find the right decorator
- **Documentation**: Each type can be documented separately
- **Maintenance**: Changes to one type don't affect the other

### **Consequences**

**Positive**:
- Clear decorator types
- Better documentation
- Reduced confusion for users

**Negative**:
- Slightly more files
- Need to document the distinction

### **Alternatives Considered**

1. **Single decorators file**: Rejected - too monolithic
2. **Separate decorator packages**: Rejected - over-engineered
3. **Keep in endpoints**: Rejected - wrong location

---

## ADR-003: Common → Utils Rename

**Date**: 2025-10-19
**Status**: ✅ Accepted
**Deciders**: Development Team

### **Context**

The `common/` module name was generic and didn't clearly indicate its purpose. Users were unsure what belonged there.

### **Decision**

Use `utils/` module for utility functions:
- Provides clear, descriptive naming
- Follows Python conventions
- Allows for organized utility categories

### **Rationale**

- **Clarity**: "utils" is more descriptive than "common"
- **Convention**: "utils" is a Python convention
- **Expansion**: Allows adding more utility categories

### **Consequences**

**Positive**:
- Clearer module purpose
- Room for utility expansion
- Consistent with Python ecosystem

### **Alternatives Considered**

1. **Keep as common**: Rejected - unclear naming
2. **Immediate change**: Rejected - would disrupt users
3. **Rename to helpers**: Rejected - less conventional

---

## ADR-004: Response Consolidation

**Date**: 2025-10-19
**Status**: ✅ Accepted
**Deciders**: Development Team

### **Context**

API response handling was fragmented across 4 files:
- `formatter.py`
- `types.py`
- `response.py`
- `helpers.py`

This created confusion about where to find response-related functionality.

### **Decision**

Consolidate all response logic into a single `api/endpoints/response.py` file containing:
- Response types (`EndpointResponse`, `APIResponse`)
- Formatting functions (`format_response()`)
- Helper methods (status code helpers)

### **Rationale**

- **Cohesion**: Related functionality in one place
- **Discoverability**: One place to look for response logic
- **Maintenance**: Easier to update response handling
- **Simplicity**: Fewer files to navigate

### **Consequences**

**Positive**:
- Single source of truth for responses
- Easier to understand
- Reduced file count

**Negative**:
- Larger single file (~400 lines)
- Need to update imports

### **Alternatives Considered**

1. **Keep fragmented**: Rejected - poor cohesion
2. **Create response package**: Rejected - over-engineering
3. **Split by HTTP status**: Rejected - awkward

---

## ADR-005: Storage Interfaces

**Date**: 2025-10-20
**Status**: ✅ Accepted
**Deciders**: Development Team

### **Context**

Storage module used `interfaces/` for both abstract base classes and concrete implementations. There was consideration to rename to `providers/`.

### **Decision**

**Keep `interfaces/` as is** because:
- Technically correct (defines interfaces/protocols)
- Follows Python convention
- Contains both abstract and concrete implementations
- Clear and understood by developers

### **Rationale**

- **Correctness**: "Interface" is the correct term
- **Convention**: Matches Python typing conventions
- **Clarity**: Developers understand "interface"
- **Stability**: No benefit to changing

### **Consequences**

**Positive**:
- Technically accurate naming
- No refactoring required
- Familiar to Python developers

**Negative**:
- None identified

### **Alternatives Considered**

1. **Rename to providers**: Rejected - less accurate
2. **Split into interfaces/ and providers/**: Rejected - over-engineering
3. **Use backends/**: Rejected - less clear

---

## ADR-006: Core Structure

**Date**: 2025-10-20
**Status**: ✅ Accepted
**Deciders**: Development Team

### **Context**

There was consideration to move all entities into a `core/entities/` subdirectory and walker into `core/entities/walker/`.

### **Decision**

**Keep flat structure** where:
- Entity classes remain at `core/` level (`object.py`, `node.py`, etc.)
- Supporting modules go in subdirectories (`walker/`)
- `walker_class.py` stays at core level (not renamed to `walker.py`)

### **Rationale**

- **Consistency**: All main entity classes at same level
- **Simplicity**: Flat is better than nested
- **Clarity**: Easy to find main classes
- **Convention**: Supporting modules in subdirs

### **Consequences**

**Positive**:
- Consistent structure
- Easy to navigate
- Clear hierarchy (classes vs. modules)

**Negative**:
- Slightly longer `core/` directory

### **Alternatives Considered**

1. **Move all to entities/**: Rejected - creates inconsistency
2. **Rename walker_class.py**: Rejected - would conflict with walker/ dir
3. **Deeper nesting**: Rejected - unnecessary complexity

---

## ADR-007: Type System

**Date**: 2025-10-19
**Status**: ✅ Accepted
**Deciders**: Development Team

### **Context**

Type hints were scattered across the codebase with no central type definitions. This led to inconsistent typing and difficulty maintaining type safety.

### **Decision**

Create comprehensive type system in `utils/types.py`:
- **Type Aliases**: `NodeId`, `EdgeId`, `WalkerId`, etc.
- **Type Guards**: `is_string()`, `is_dict()`, etc.
- **Type Converters**: `to_string()`, `to_dict()`, etc.
- **Complex Types**: `GraphData`, `APIResponse`, etc.

### **Rationale**

- **Consistency**: Central source for type definitions
- **Safety**: Better type checking with mypy/pyright
- **Documentation**: Types as documentation
- **Reusability**: DRY principle for types

### **Consequences**

**Positive**:
- Improved type safety
- Better IDE autocomplete
- Clear type contracts
- Easier refactoring

**Negative**:
- Learning curve for new types
- Need to maintain type definitions

### **Alternatives Considered**

1. **Keep types scattered**: Rejected - poor maintainability
2. **Use only built-in types**: Rejected - less expressive
3. **Create separate types package**: Rejected - over-engineering

---

## ADR-008: Context Management

**Date**: 2025-10-19
**Status**: ✅ Accepted
**Deciders**: Development Team

### **Context**

Multiple context managers existed with unclear hierarchy and usage patterns:
- `GraphContext` (core)
- `ServerContext` (api)
- `GlobalContext` (utils)

Users were confused about when to use each.

### **Decision**

Establish clear hierarchy and document:

1. **GlobalContext** (utils) - Base context for any global state
2. **GraphContext** (core) - Database and graph operations
3. **ServerContext** (api) - Server-specific state

Create comprehensive documentation (`context-management-guide.md`).

### **Rationale**

- **Clarity**: Clear when to use each context
- **Hierarchy**: Logical dependency chain
- **Flexibility**: Can be used independently or composed
- **Documentation**: Comprehensive guide

### **Consequences**

**Positive**:
- Clear context usage patterns
- Better documentation
- Proper separation of concerns

**Negative**:
- Multiple context types to learn
- Need to understand hierarchy

### **Alternatives Considered**

1. **Single unified context**: Rejected - too monolithic
2. **Remove GlobalContext**: Rejected - useful pattern
3. **Rename contexts**: Rejected - current names are clear

---

## 🔍 **Decision-Making Framework**

When making architectural decisions, we consider:

1. **Simplicity**: Is it easy to understand?
2. **Maintainability**: Can we maintain it long-term?
3. **Scalability**: Will it grow with the project?
4. **Convention**: Does it follow Python/industry standards?
5. **User Impact**: How does it affect library users?

---

## 📚 **Related Documentation**

- [Module Responsibility Matrix](module-responsibility-matrix.md)
- [Import Patterns](import-patterns.md)
- [Context Management Guide](context-management-guide.md)
- [Decorator Reference](decorator-reference.md)

---

**Last Updated**: 2025-10-20
**Version**: 0.0.1
**Maintainer**: JVspatial Team

