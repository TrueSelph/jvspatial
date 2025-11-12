# Migration Guide

This guide helps you migrate existing applications **from other libraries** to jvspatial, covering common scenarios and patterns for adopting jvspatial in your projects.

## Table of Contents

- [From SQLAlchemy](#from-sqlalchemy)
- [From Django ORM](#from-django-orm)
- [From MongoDB/Motor](#from-mongodb-motor)
- [From Raw SQL](#from-raw-sql)
- [From Neo4j](#from-neo4j)
- [Migration Strategies](#migration-strategies)

## From SQLAlchemy

### Models

**SQLAlchemy:**
```python
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship

class City(Base):
    __tablename__ = "cities"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    population = Column(Integer)
    latitude = Column(Float)
    longitude = Column(Float)

    # Relationships via foreign keys
    roads = relationship("Road", back_populates="source_city")

class Road(Base):
    __tablename__ = "roads"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    distance = Column(Float)
    source_city_id = Column(Integer, ForeignKey("cities.id"))
    dest_city_id = Column(Integer, ForeignKey("cities.id"))

    # Relationships
    source_city = relationship("City", back_populates="roads")
    dest_city = relationship("City")
```

**jvspatial:**
```python
from jvspatial.core import Node, Edge

class City(Node):
    name: str
    population: int
    latitude: float
    longitude: float

class Road(Edge):
    name: str
    distance: float

# Relationships are direct
nyc = await City.create(name="New York", population=8_400_000)
boston = await City.create(name="Boston", population=675_000)
i95 = await Road.create(src=nyc, dst=boston, distance=215.0)
```

### Queries

**SQLAlchemy:**
```python
# Complex join query
cities = (
    session.query(City)
    .join(Road, City.id == Road.source_city_id)
    .filter(
        City.population > 1_000_000,
        Road.distance < 500
    )
    .order_by(City.population.desc())
    .all()
)

# Count with conditions
count = (
    session.query(City)
    .filter(City.population > 1_000_000)
    .count()
)
```

**jvspatial:**
```python
# Semantic graph queries
cities = await City.find({
    "context.population": {"$gt": 1_000_000},
    "edge": [{
        "Road": {"context.distance": {"$lt": 500}}
    }]
})

# Simple counting
count = await City.count({
    "context.population": {"$gt": 1_000_000}
})
```

### Relationships

**SQLAlchemy:**
```python
# Get related cities through roads
connected_cities = [
    road.dest_city
    for road in city.roads
]

# Add relationship
new_road = Road(
    source_city=city1,
    dest_city=city2,
    distance=100
)
session.add(new_road)
```

**jvspatial:**
```python
# Get connected cities
connected = await city.nodes(
    node=City,
    edge=Road
)

# Add relationship
new_road = await city1.connect(
    city2,
    Road,
    distance=100
)
```

## From Django ORM

### Models

**Django:**
```python
from django.db import models

class City(models.Model):
    name = models.CharField(max_length=100)
    population = models.IntegerField()
    latitude = models.FloatField()
    longitude = models.FloatField()

class Road(models.Model):
    name = models.CharField(max_length=100)
    distance = models.FloatField()
    source_city = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        related_name="roads_from"
    )
    dest_city = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        related_name="roads_to"
    )
```

**jvspatial:**
```python
from jvspatial.core import Node, Edge

class City(Node):
    name: str
    population: int
    latitude: float
    longitude: float

class Road(Edge):
    name: str
    distance: float
```

### Queries

**Django:**
```python
# Complex filters
cities = (
    City.objects
    .filter(population__gt=1_000_000)
    .filter(roads_from__distance__lt=500)
    .order_by("-population")
)

# Aggregation
from django.db.models import Avg
avg_population = (
    City.objects
    .filter(population__gt=100_000)
    .aggregate(Avg("population"))
)
```

**jvspatial:**
```python
# Semantic filtering
cities = await City.find({
    "context.population": {"$gt": 1_000_000},
    "edge": [{
        "Road": {"context.distance": {"$lt": 500}}
    }]
})

# Aggregation
stats = await City.aggregate([
    {"$match": {"context.population": {"$gt": 100_000}}},
    {"$group": {
        "_id": None,
        "avg_population": {"$avg": "$context.population"}
    }}
])
```

## From MongoDB/Motor

### Schema

**MongoDB/Motor:**
```python
# No schema validation
city = {
    "name": "New York",
    "population": 8_400_000,
    "location": {
        "type": "Point",
        "coordinates": [-74.006, 40.7128]
    }
}

road = {
    "name": "I-95",
    "distance": 215.0,
    "source_city_id": ObjectId("..."),
    "dest_city_id": ObjectId("...")
}
```

**jvspatial:**
```python
from jvspatial.core import Node, Edge

class City(Node):
    name: str
    population: int
    latitude: float
    longitude: float

class Road(Edge):
    name: str
    distance: float

# Type-safe creation
nyc = await City.create(
    name="New York",
    population=8_400_000,
    latitude=40.7128,
    longitude=-74.006
)
```

### Queries

**MongoDB/Motor:**
```python
# Raw MongoDB queries
cities = await db.cities.find({
    "population": {"$gt": 1_000_000},
    "location": {
        "$near": {
            "$geometry": {
                "type": "Point",
                "coordinates": [-74, 40]
            },
            "$maxDistance": 100000
        }
    }
})

# Manual relationship traversal
async def get_connected_cities(city_id):
    roads = await db.roads.find({
        "source_city_id": city_id
    })
    dest_ids = [r["dest_city_id"] for r in roads]
    return await db.cities.find({
        "_id": {"$in": dest_ids}
    })
```

**jvspatial:**
```python
# Type-safe queries
cities = await City.find({
    "context.population": {"$gt": 1_000_000},
    "context.location": {
        "$near": {"latitude": 40, "longitude": -74},
        "$maxDistance": 100
    }
})

# Graph traversal
connected = await city.nodes(
    node=City,
    edge=Road,
    distance={"$lte": 100}
)
```

## From Raw SQL

### Schema

**SQL:**
```sql
CREATE TABLE cities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    population INTEGER,
    latitude FLOAT,
    longitude FLOAT
);

CREATE TABLE roads (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    distance FLOAT,
    source_city_id INTEGER REFERENCES cities(id),
    dest_city_id INTEGER REFERENCES cities(id)
);
```

**jvspatial:**
```python
from jvspatial.core import Node, Edge

class City(Node):
    name: str
    population: int
    latitude: float
    longitude: float

class Road(Edge):
    name: str
    distance: float
```

### Queries

**SQL:**
```sql
-- Complex joins
SELECT c.*
FROM cities c
JOIN roads r ON c.id = r.source_city_id
WHERE c.population > 1000000
AND r.distance < 500
ORDER BY c.population DESC;

-- Aggregation
SELECT
    AVG(population) as avg_pop,
    COUNT(*) as total
FROM cities
WHERE population > 100000;
```

**jvspatial:**
```python
# Graph queries
cities = await City.find({
    "context.population": {"$gt": 1_000_000},
    "edge": [{
        "Road": {"context.distance": {"$lt": 500}}
    }]
})

# Aggregation
stats = await City.aggregate([
    {"$match": {"context.population": {"$gt": 100_000}}},
    {"$group": {
        "_id": None,
        "avg_pop": {"$avg": "$context.population"},
        "total": {"$sum": 1}
    }}
])
```

## From Neo4j

### Schema

**Neo4j/Cypher:**
```cypher
CREATE (c:City {
    name: "New York",
    population: 8400000,
    latitude: 40.7128,
    longitude: -74.006
})

CREATE (c1:City)-[:ROAD {
    name: "I-95",
    distance: 215.0
}]->(c2:City)
```

**jvspatial:**
```python
from jvspatial.core import Node, Edge

class City(Node):
    name: str
    population: int
    latitude: float
    longitude: float

class Road(Edge):
    name: str
    distance: float

# Create cities and connect
nyc = await City.create(
    name="New York",
    population=8_400_000,
    latitude=40.7128,
    longitude=-74.006
)

boston = await City.create(
    name="Boston",
    population=675_000,
    latitude=42.3601,
    longitude=-71.0589
)

i95 = await Road.create(
    src=nyc,
    dst=boston,
    name="I-95",
    distance=215.0
)
```

### Queries

**Neo4j/Cypher:**
```cypher
// Path traversal
MATCH (c:City)-[r:ROAD]->(connected:City)
WHERE c.population > 1000000
AND r.distance < 500
RETURN connected;

// Pattern matching
MATCH (c1:City)-[r:ROAD*1..3]->(c2:City)
WHERE c1.name = "New York"
RETURN c2;
```

**jvspatial:**
```python
# Direct traversal
connected = await city.nodes(
    node=City,
    edge=Road,
    distance={"$lt": 500}
)

# Walker for complex patterns
class PathFinder(Walker):
    @on_visit(City)
    async def find_paths(self, here: City):
        if self.current_depth() > 3:
            return

        cities = await here.nodes(
            node=City,
            edge=Road
        )
        await self.visit(cities)
```

## Migration Strategies

### Incremental Migration

1. **Start with Core Models**
   ```python
   # Step 1: Create Node/Edge classes
   class City(Node):
       name: str
       population: int

   # Step 2: Keep existing models temporarily
   class LegacyCity(Base):
       __tablename__ = "cities"
   ```

2. **Data Migration**
   ```python
   async def migrate_cities():
       # Read from old system
       legacy_cities = LegacyCity.query.all()

       # Create in jvspatial
       for city in legacy_cities:
           await City.create(
               name=city.name,
               population=city.population
           )
   ```

3. **Dual Write Period**
   ```python
   async def create_city(data):
       # Write to both systems
       legacy_city = LegacyCity(**data)
       session.add(legacy_city)

       new_city = await City.create(**data)
       return new_city
   ```

### Hybrid Access

```python
class CityService:
    def __init__(self, use_new_system: bool = False):
        self.use_new_system = use_new_system

    async def get_city(self, city_id: str):
        if self.use_new_system:
            return await City.get(city_id)
        else:
            return session.query(LegacyCity).get(city_id)
```

### Feature Flags

```python
from feature_flags import FLAGS

async def get_nearby_cities(city_id: str):
    if FLAGS.use_jvspatial_queries:
        city = await City.get(city_id)
        return await city.nodes(
            node=City,
            edge=Road,
            distance={"$lt": 100}
        )
    else:
        # Legacy query
        return legacy_get_nearby(city_id)
```

## Best Practices

1. **Start Small**
   - Migrate one model at a time
   - Begin with read-only access
   - Gradually add write operations

2. **Validate Data**
   - Compare results between systems
   - Run parallel queries
   - Verify relationships

3. **Monitor Performance**
   - Compare query times
   - Check memory usage
   - Monitor error rates

4. **Plan Rollback**
   - Keep legacy system running
   - Maintain data backups
   - Document rollback procedures

## See Also

- [Design Decisions](design-decisions.md)
- [Core Concepts](core-concepts.md)
- [API Reference](rest-api.md)
- [Best Practices](best-practices.md)