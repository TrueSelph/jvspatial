# Caching System in jvspatial

The jvspatial caching system provides transparent, high-performance entity caching with pluggable backends designed for different deployment scenarios. The caching layer automatically caches entities as you work with them using the standard entity-centric API, dramatically reducing database queries and improving response times.

## Overview

jvspatial's caching system features:

- **Transparent Operation**: Caching works automatically with standard entity operations
- **Pluggable Architecture**: Swap cache backends without changing application code
- **Multiple Strategies**: In-memory, Redis, and layered caching for different use cases
- **Environment-Based Configuration**: Configure caching via environment variables or `.env` files
- **Statistics & Monitoring**: Built-in cache hit/miss tracking for performance tuning
- **TTL Support**: Optional time-to-live for automatic cache expiration
- **LRU Eviction**: Automatic least-recently-used eviction when cache is full

## Quick Start

### Basic Caching (Automatic)

Caching is enabled by default and works transparently with the entity-centric API:

```python
from jvspatial.core import Node

class User(Node):
    name: str = ""
    email: str = ""
    department: str = ""

# CREATE - Entity is automatically cached
user = await User.create(name="Alice", email="alice@company.com")

# GET - First access fetches from database and caches
retrieved1 = await User.get(user.id)  # Database query + cache store

# GET - Subsequent accesses use cache (no database query!)
retrieved2 = await User.get(user.id)  # Cache hit!
retrieved3 = await User.get(user.id)  # Cache hit!

# UPDATE - Cache is automatically updated
user.email = "alice@newcompany.com"
await user.save()  # Updates database + cache

# DELETE - Cache is automatically cleared
await user.delete()  # Removes from database + cache
```

The caching system works completely transparently - you use the same entity operations (`create()`, `get()`, `save()`, `delete()`) and caching happens automatically behind the scenes.

### Environment-Based Configuration

Configure caching behavior via environment variables in `.env` file:

```env
# Use in-memory caching (default)
JVSPATIAL_CACHE_BACKEND=memory
JVSPATIAL_CACHE_SIZE=1000

# Disable caching completely
JVSPATIAL_CACHE_SIZE=0

# Use Redis caching for distributed deployments
JVSPATIAL_CACHE_BACKEND=redis
JVSPATIAL_REDIS_URL=redis://localhost:6379
JVSPATIAL_REDIS_DB=0

# Use layered caching (fast local + shared Redis)
JVSPATIAL_CACHE_BACKEND=layered
JVSPATIAL_L1_SIZE=500
JVSPATIAL_REDIS_URL=redis://localhost:6379
```

## Cache Backends

### MemoryCache (Default)

Fast, local in-memory caching suitable for single-instance deployments.

**Features:**
- Sub-millisecond access latency
- LRU (Least Recently Used) eviction
- Optional TTL support
- Statistics tracking
- Zero external dependencies

**Best For:**
- Single-server deployments
- Development and testing
- Applications with predictable memory footprint
- L1 cache in layered configurations

**Configuration:**

```env
JVSPATIAL_CACHE_BACKEND=memory
JVSPATIAL_CACHE_SIZE=1000  # Max items (0 to disable)
```

**Example Usage:**

```python
from jvspatial.core import Node

class Product(Node):
    name: str = ""
    price: float = 0.0
    sku: str = ""

# Caching works automatically with default memory backend
product = await Product.create(name="Widget", price=29.99)
cached = await Product.get(product.id)  # Uses memory cache
```

### RedisCache

Distributed Redis-backed cache for multi-instance deployments requiring shared cache state.

**Features:**
- Distributed caching across multiple application instances
- Automatic serialization/deserialization
- TTL support with Redis expiration
- Connection pooling
- Atomic operations

**Best For:**
- Multi-server deployments
- Microservices architectures
- Applications requiring shared cache state
- Horizontal scaling scenarios

**Configuration:**

```env
JVSPATIAL_CACHE_BACKEND=redis
JVSPATIAL_REDIS_URL=redis://localhost:6379
JVSPATIAL_REDIS_DB=0
JVSPATIAL_REDIS_PASSWORD=your-redis-password
JVSPATIAL_REDIS_PREFIX=jvspatial  # Optional key prefix
```

**Example Usage:**

```python
# Configure via environment (recommended)
# Then use normal entity operations
from jvspatial.core import Node

class User(Node):
    name: str = ""
    email: str = ""

# All operations use Redis cache automatically
user = await User.create(name="Bob", email="bob@company.com")
retrieved = await User.get(user.id)  # Checks Redis first
```

**Installation:**

Redis caching requires the `redis` package:

```bash
pip install jvspatial[redis]
# or
pip install redis
```

### LayeredCache

Two-tier cache combining fast local memory (L1) with shared Redis (L2) for optimal performance in distributed deployments.

**Features:**
- Fast local L1 cache for frequently accessed data
- Shared L2 Redis cache for distributed access
- Automatic promotion from L2 to L1 on cache hits
- Write-through to both layers
- Best of both worlds: speed + distribution

**Best For:**
- Production multi-server deployments
- Applications with hot and cold data patterns
- Scenarios requiring both speed and distribution
- Large-scale systems with regional data access patterns

**Configuration:**

```env
JVSPATIAL_CACHE_BACKEND=layered
JVSPATIAL_L1_SIZE=500              # L1 memory cache size
JVSPATIAL_REDIS_URL=redis://localhost:6379
JVSPATIAL_REDIS_DB=0
```

**Example Usage:**

```python
# Configure via environment
# Entity operations automatically use layered cache
from jvspatial.core import Node

class City(Node):
    name: str = ""
    population: int = 0

# L1 (memory) checked first, then L2 (Redis), then database
city = await City.create(name="San Francisco", population=800000)
retrieved = await City.get(city.id)  # Transparent layered caching
```

**Installation:**

Layered caching requires the `redis` package:

```bash
pip install jvspatial[redis]
```

## How Caching Works with Entities

The caching system integrates seamlessly with all entity operations:

### Entity Lifecycle and Caching

```python
from jvspatial.core import Node

class User(Node):
    name: str = ""
    email: str = ""
    active: bool = True

# 1. CREATE - Entity is cached immediately
user = await User.create(name="Alice", email="alice@company.com")
# State: Database has user, cache has user

# 2. GET - Check cache first, then database
retrieved = await User.get(user.id)
# First call: Cache miss → database query → cache store
# Subsequent calls: Cache hit → no database query

# 3. FIND - Results are NOT cached (too dynamic)
users = await User.find({"context.active": True})
# These go to database each time (filtering can change)

# 4. UPDATE - Cache is automatically updated
user.email = "alice@newcompany.com"
await user.save()
# State: Database updated, cache updated

# 5. DELETE - Cache entry is automatically removed
await user.delete()
# State: Database record deleted, cache entry removed
```

### Query Operations

```python
# Individual entity retrievals use cache
user = await User.get(user_id)  # Cached

# Bulk queries always hit database
users = await User.find({"context.department": "engineering"})  # Not cached
all_users = await User.all()  # Not cached

# Count and distinct operations hit database
count = await User.count({"context.active": True})  # Not cached
depts = await User.distinct("department")  # Not cached
```

**Why aren't queries cached?** Query results can change frequently and are often filtered differently each time. Caching individual entities by ID provides better hit rates and more predictable behavior.

## Performance Optimization

### Monitoring Cache Performance

You can access cache statistics through the internal GraphContext (use sparingly for monitoring only):

```python
from jvspatial.core import get_default_context

# Get cache statistics (monitoring purposes only)
ctx = get_default_context()
stats = ctx.get_cache_stats()

print(f"Cache Performance:")
print(f"  Total Requests: {stats['total_requests']}")
print(f"  Cache Hits: {stats['cache_hits']}")
print(f"  Cache Misses: {stats['cache_misses']}")
print(f"  Hit Rate: {stats['hit_rate']:.2%}")
print(f"  Cache Size: {stats['cache_size']}")

# Good performance indicators
hit_rate = stats['hit_rate']
if hit_rate > 0.80:
    print("Excellent cache performance!")
elif hit_rate > 0.50:
    print("Good cache performance")
else:
    print("Consider increasing cache size")
```

### Choosing the Right Cache Size

```env
# Small deployments (< 1,000 entities)
JVSPATIAL_CACHE_SIZE=500

# Medium deployments (1,000 - 100,000 entities)
JVSPATIAL_CACHE_SIZE=5000

# Large deployments (> 100,000 entities)
JVSPATIAL_CACHE_SIZE=10000

# Memory-constrained environments
JVSPATIAL_CACHE_SIZE=100
```

### Cache Warming Strategy

Pre-populate the cache with frequently accessed entities:

```python
async def warm_cache():
    """Pre-populate cache with frequently accessed entities."""

    # Load frequently accessed users (warms the cache)
    active_users = await User.find({"context.active": True})
    for user in active_users[:100]:  # Top 100 active users
        await User.get(user.id)  # Populates cache

    # Load frequently accessed products
    popular_products = await Product.find({
        "context.views": {"$gte": 1000}
    })
    for product in popular_products:
        await Product.get(product.id)  # Populates cache

    print(f"Cache warmed with frequently accessed entities")
```

### Access Patterns for Best Performance

```python
# ✅ GOOD: Repeated access to same entities by ID
user = await User.get(user_id)  # Cache hit after first access
user = await User.get(user_id)  # Cache hit
user = await User.get(user_id)  # Cache hit

# ❌ LESS OPTIMAL: Always using find() for single entities
users = await User.find({"context.email": "alice@company.com"})  # Database hit
users = await User.find({"context.email": "alice@company.com"})  # Database hit

# ✅ BETTER: Get ID from first find, then use get()
users = await User.find({"context.email": "alice@company.com"})
if users:
    user_id = users[0].id
    # Future accesses by ID will use cache
    user = await User.get(user_id)  # Cached!
```

## Production Considerations

### Memory Usage

Monitor cache memory usage in production:

```python
from jvspatial.core import get_default_context

# Check cache statistics
ctx = get_default_context()
stats = ctx.get_cache_stats()

cache_size = stats.get('cache_size', 0)
max_size = stats.get('max_size', 1000)
utilization = cache_size / max_size if max_size > 0 else 0

print(f"Cache Utilization: {utilization:.1%}")

if utilization > 0.90:
    print("Cache is full - consider increasing size")
elif utilization < 0.30:
    print("Cache is underutilized - size may be too large")
```

### Distributed Deployments

For multi-server deployments, use Redis or LayeredCache:

```env
# Production configuration
JVSPATIAL_CACHE_BACKEND=layered
JVSPATIAL_L1_SIZE=500              # Local cache per instance
JVSPATIAL_REDIS_URL=redis://redis-cluster:6379
JVSPATIAL_REDIS_DB=0
JVSPATIAL_REDIS_PASSWORD=${REDIS_PASSWORD}
```

### Cache Invalidation

Cache is automatically invalidated on entity updates and deletes:

```python
# Cache is automatically managed
user = await User.get(user_id)  # Cached

# Update automatically refreshes cache
user.name = "Updated Name"
await user.save()  # Database updated + cache refreshed

# Delete automatically removes from cache
await user.delete()  # Database deleted + cache cleared
```

Manual cache clearing (use sparingly, mainly for testing):

```python
from jvspatial.core import get_default_context

# Clear entire cache (e.g., after schema migrations)
ctx = get_default_context()
await ctx.clear_cache()
```

## Disabling Cache

To disable caching entirely:

```env
# Via environment variable
JVSPATIAL_CACHE_SIZE=0
```

When caching is disabled, all entity operations go directly to the database with no caching overhead.

## Troubleshooting

### Low Cache Hit Rate

If cache hit rate is below 50%:

1. **Increase cache size**: More entities can be cached
   ```env
   JVSPATIAL_CACHE_SIZE=5000
   ```

2. **Analyze access patterns**: Use `get()` instead of `find()` for repeated access
   ```python
   # Instead of repeated finds
   users = await User.find({"context.email": email})

   # Cache the ID and use get()
   user_id = users[0].id if users else None
   user = await User.get(user_id)  # Uses cache
   ```

3. **Implement cache warming**: Pre-populate cache with hot data
   ```python
   await warm_cache()  # See Cache Warming Strategy above
   ```

### Memory Issues

If experiencing memory pressure:

1. **Reduce cache size**
   ```env
   JVSPATIAL_CACHE_SIZE=500
   ```

2. **Use layered cache** (smaller local cache)
   ```env
   JVSPATIAL_CACHE_BACKEND=layered
   JVSPATIAL_L1_SIZE=200
   ```

3. **Disable caching if not beneficial**
   ```env
   JVSPATIAL_CACHE_SIZE=0
   ```

### Redis Connection Issues

For Redis-based caching, ensure Redis is accessible:

```python
# Test Redis connectivity
from jvspatial.core import Object

class TestEntity(Object):
    value: str = ""

try:
    # If this works, Redis cache is functional
    entity = await TestEntity.create(value="test")
    retrieved = await TestEntity.get(entity.id)
    print("Redis cache working")
except Exception as e:
    print(f"Cache issue: {e}")
    # Check JVSPATIAL_REDIS_URL environment variable
```

## Best Practices

1. **Do**: Configure via `.env` files
2. **Do**: Let caching work transparently with entity-centric operations
3. **Do**: Use `Entity.get(id)` for cache efficiency
4. **Do**: Track hit rates in production
5. **Do**: Use layered caching for distributed systems
6. **Do**: Pre-populate frequently accessed entities
7. **Don't**: Avoid direct database calls (bypass entities)
8. **Don't**: Over-rely on find() (use get() for individual entities)

## Configuration Reference

### Environment Variables

| Variable | Description | Default | Values |
|----------|-------------|---------|--------|
| `JVSPATIAL_CACHE_BACKEND` | Cache backend type | `memory` | `memory`, `redis`, `layered` |
| `JVSPATIAL_CACHE_SIZE` | Maximum cache size (0=disabled) | `1000` | Any positive integer |
| `JVSPATIAL_REDIS_URL` | Redis connection URL | `redis://localhost:6379` | Any valid Redis URL |
| `JVSPATIAL_REDIS_DB` | Redis database number | `0` | 0-15 (typically) |
| `JVSPATIAL_REDIS_PASSWORD` | Redis password | None | Any string |
| `JVSPATIAL_REDIS_PREFIX` | Redis key prefix | `jvspatial` | Any string |
| `JVSPATIAL_L1_SIZE` | L1 cache size (layered) | `500` | Any positive integer |

### Example Configurations

**Development (default):**
```env
JVSPATIAL_CACHE_BACKEND=memory
JVSPATIAL_CACHE_SIZE=1000
```

**Production (single server):**
```env
JVSPATIAL_CACHE_BACKEND=memory
JVSPATIAL_CACHE_SIZE=10000
```

**Production (distributed):**
```env
JVSPATIAL_CACHE_BACKEND=layered
JVSPATIAL_L1_SIZE=500
JVSPATIAL_REDIS_URL=redis://redis.prod:6379
JVSPATIAL_REDIS_PASSWORD=${REDIS_PASSWORD}
```

**Testing (caching disabled):**
```env
JVSPATIAL_CACHE_SIZE=0
```

## Related Documentation

- **[Environment Configuration](environment-configuration.md)**: Complete environment setup guide
- **[Entity Reference](entity-reference.md)**: Entity operations and lifecycle
- **[GraphContext](graph-context.md)**: Low-level context management (advanced)
- **[MongoDB Query Interface](mongodb-query-interface.md)**: Query patterns and filtering

---

**Need Help?**
- Issues: [GitHub Issues](https://github.com/TrueSelph/jvspatial/issues)
- Discussions: [GitHub Discussions](https://github.com/TrueSelph/jvspatial/discussions)