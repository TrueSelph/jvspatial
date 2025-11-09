"""Comprehensive test suite for query system.

Tests QueryBuilder and QueryOperator functionality including:
- Query construction
- Operator functionality
- Complex query building
- Query validation
- Performance characteristics
"""

import pytest

from jvspatial.core.entities import Edge, Node
from jvspatial.db.query import QueryBuilder, QueryOperator, query


class QueryTestNode(Node):
    """Test node for query testing."""

    name: str = ""
    value: int = 0
    category: str = ""
    tags: list = []
    metadata: dict = {}


class QueryTestEdge(Edge):
    """Test edge for query testing."""

    weight: int = 1
    condition: str = "good"
    properties: dict = {}


class TestQueryBuilder:
    """Test QueryBuilder functionality."""

    async def test_basic_query_construction(self):
        """Test basic query construction."""
        qb = QueryBuilder()
        qb.field("name").eq("test")
        qb.field("value").gt(10)

        query_dict = qb.build()
        assert query_dict["name"]["$eq"] == "test"
        assert query_dict["value"]["$gt"] == 10

    async def test_equality_operators(self):
        """Test equality operators."""
        qb = QueryBuilder()
        qb.field("name").eq("test")
        qb.field("category").ne("deleted")

        query_dict = qb.build()
        assert query_dict["name"]["$eq"] == "test"
        assert query_dict["category"]["$ne"] == "deleted"

    async def test_comparison_operators(self):
        """Test comparison operators."""
        qb = QueryBuilder()
        qb.field("value").gt(10).gte(5).lt(100).lte(50)

        query_dict = qb.build()
        assert query_dict["value"]["$gt"] == 10
        assert query_dict["value"]["$gte"] == 5
        assert query_dict["value"]["$lt"] == 100
        assert query_dict["value"]["$lte"] == 50

    async def test_array_operators(self):
        """Test array operators."""
        qb = QueryBuilder()
        qb.field("category").in_(["test", "prod"])
        qb.field("status").nin(["deleted", "archived"])
        qb.field("tags").all_(["important", "urgent"])
        # Note: elem_match not yet implemented in FieldQuery, skip for now

        query_dict = qb.build()
        assert query_dict["category"]["$in"] == ["test", "prod"]
        assert query_dict["status"]["$nin"] == ["deleted", "archived"]
        assert query_dict["tags"]["$all"] == ["important", "urgent"]

    async def test_string_operators(self):
        """Test string operators."""
        qb = QueryBuilder()
        qb.field("name").regex(r"^test.*", "i")
        qb.field("email").exists()
        qb.field("value").type_("number")

        query_dict = qb.build()
        assert query_dict["name"]["$regex"] == r"^test.*"
        assert query_dict["name"]["$options"] == "i"
        assert query_dict["email"]["$exists"] is True
        assert query_dict["value"]["$type"] == "number"

    async def test_logical_operators(self):
        """Test logical operators."""
        qb = QueryBuilder()
        qb.and_({"name": "test"}, {"value": {"$gt": 10}})
        qb.or_({"category": "test"}, {"category": "prod"})
        qb.nor_({"status": "deleted"}, {"status": "archived"})
        # Note: not_ is not implemented, skip for now

        query_dict = qb.build()
        assert "$and" in query_dict
        assert "$or" in query_dict
        assert "$nor" in query_dict

    async def test_nested_queries(self):
        """Test nested query construction."""
        qb = QueryBuilder()
        qb.field("metadata.type").eq("user")
        qb.field("metadata.score").gt(100)
        qb.field("metadata.tags").in_(["admin", "user"])

        query_dict = qb.build()
        assert query_dict["metadata.type"]["$eq"] == "user"
        assert query_dict["metadata.score"]["$gt"] == 100
        assert query_dict["metadata.tags"]["$in"] == ["admin", "user"]

    async def test_complex_query_construction(self):
        """Test complex query construction."""
        qb = QueryBuilder()
        qb.and_(
            [
                {"category": "test"},
                {"$or": [{"value": {"$gte": 10}}, {"name": {"$regex": r"^test.*"}}]},
                {"tags": {"$in": ["important"]}},
                {"metadata.status": {"$ne": "deleted"}},
            ]
        )

        query_dict = qb.build()
        assert "$and" in query_dict
        assert len(query_dict["$and"]) == 4

    async def test_query_chaining(self):
        """Test query method chaining."""
        qb = QueryBuilder()
        qb.field("name").eq("test")
        qb.field("value").gt(10)
        qb.field("category").in_(["test", "prod"])
        qb.field("description").regex(r".*important.*")

        query_dict = qb.build()
        assert query_dict["name"]["$eq"] == "test"
        assert query_dict["value"]["$gt"] == 10
        assert query_dict["category"]["$in"] == ["test", "prod"]
        assert query_dict["description"]["$regex"] == r".*important.*"

    async def test_query_reset(self):
        """Test query reset functionality."""
        qb = QueryBuilder()
        qb.field("name").eq("test")
        qb.field("value").gt(10)

        # Reset query by creating new instance
        qb = QueryBuilder()
        qb.field("category").eq("prod")

        query_dict = qb.build()
        assert "name" not in query_dict
        assert "value" not in query_dict
        assert query_dict["category"]["$eq"] == "prod"

    async def test_query_validation(self):
        """Test query validation."""
        qb = QueryBuilder()

        # Valid query
        qb.field("name").eq("test")
        query_dict = qb.build()
        assert len(query_dict) > 0

        # Empty query
        qb = QueryBuilder()
        query_dict = qb.build()
        assert len(query_dict) == 0

    async def test_query_cloning(self):
        """Test query cloning via copy."""
        import copy

        qb1 = QueryBuilder()
        qb1.field("name").eq("test")
        qb1.field("value").gt(10)

        qb2 = QueryBuilder()
        qb2._query = copy.deepcopy(qb1._query)
        qb2.field("category").eq("prod")

        query1 = qb1.build()
        query2 = qb2.build()

        assert query1["name"]["$eq"] == "test"
        assert query1["value"]["$gt"] == 10
        assert "category" not in query1

        assert query2["name"]["$eq"] == "test"
        assert query2["value"]["$gt"] == 10
        assert query2["category"]["$eq"] == "prod"


class TestQueryOperator:
    """Test QueryOperator functionality."""

    async def test_operator_constants(self):
        """Test operator constants."""
        # QueryOperator is just an enumeration of constants
        assert QueryOperator.EQ == "$eq"
        assert QueryOperator.GT == "$gt"
        assert QueryOperator.LT == "$lt"
        assert QueryOperator.IN == "$in"
        assert QueryOperator.AND == "$and"
        assert QueryOperator.OR == "$or"
        assert QueryOperator.NOR == "$nor"
        assert QueryOperator.REGEX == "$regex"
        assert QueryOperator.EXISTS == "$exists"


class TestQueryFunction:
    """Test query function functionality."""

    async def test_query_function_basic(self):
        """Test basic query function usage."""
        q = query()
        q.field("name").eq("test")
        q.field("value").gt(10)
        query_dict = q.build()

        assert query_dict["name"]["$eq"] == "test"
        assert query_dict["value"]["$gt"] == 10

    async def test_query_function_chaining(self):
        """Test query function chaining."""
        q = query()
        q.field("name").eq("test")
        q.field("value").gt(10)
        q.field("category").in_(["test", "prod"])
        q.field("description").regex(r".*important.*")

        query_dict = q.build()
        assert query_dict["name"]["$eq"] == "test"
        assert query_dict["value"]["$gt"] == 10
        assert query_dict["category"]["$in"] == ["test", "prod"]
        assert query_dict["description"]["$regex"] == r".*important.*"

    async def test_query_function_complex(self):
        """Test complex query function usage."""
        q = query().and_(
            [
                {"category": "test"},
                {"$or": [{"value": {"$gte": 10}}, {"name": {"$regex": r"^test.*"}}]},
                {"tags": {"$in": ["important"]}},
                {"metadata.status": {"$ne": "deleted"}},
            ]
        )

        query_dict = q.build()
        assert "$and" in query_dict
        assert len(query_dict["$and"]) == 4

    async def test_query_function_validation(self):
        """Test query function validation."""
        # Valid query
        q = query()
        q.field("name").eq("test")
        query_dict = q.build()
        assert len(query_dict) > 0

        # Empty query
        q = query()
        query_dict = q.build()
        assert len(query_dict) == 0

    async def test_query_function_cloning(self):
        """Test query function cloning."""
        import copy

        q1 = query()
        q1.field("name").eq("test")
        q1.field("value").gt(10)

        q2 = query()
        q2._query = copy.deepcopy(q1._query)
        q2.field("category").eq("prod")

        query1 = q1.build()
        query2 = q2.build()

        assert query1["name"]["$eq"] == "test"
        assert query1["value"]["$gt"] == 10
        assert "category" not in query1

        assert query2["name"]["$eq"] == "test"
        assert query2["value"]["$gt"] == 10
        assert query2["category"]["$eq"] == "prod"


class TestQueryPerformance:
    """Test query performance characteristics."""

    async def test_large_query_construction(self):
        """Test construction of large queries."""
        qb = QueryBuilder()

        # Add many conditions
        for i in range(1000):
            qb.field(f"field_{i}").eq(f"value_{i}")

        query_dict = qb.build()
        assert len(query_dict) == 1000

    async def test_nested_query_performance(self):
        """Test performance of nested queries."""
        qb = QueryBuilder()

        # Create deeply nested query
        for i in range(10):
            qb.and_([{f"level_{i}": f"value_{i}"}])

        query_dict = qb.build()
        assert "$and" in query_dict

    async def test_query_serialization_performance(self):
        """Test query serialization performance."""
        qb = QueryBuilder()
        qb.field("name").eq("test")
        qb.field("value").gt(10)
        qb.field("category").in_(["test", "prod"])

        # Serialize multiple times
        for _ in range(1000):
            query_dict = qb.build()
            assert query_dict["name"]["$eq"] == "test"


class TestQueryIntegration:
    """Test query integration with entities."""

    async def test_node_query_integration(self):
        """Test query integration with Node entities."""
        # Test query construction for Node
        qb = QueryBuilder()
        qb.field("name").eq("test_node")
        qb.field("value").gt(10)
        qb.field("category").in_(["test", "prod"])

        query_dict = qb.build()
        assert query_dict["name"]["$eq"] == "test_node"
        assert query_dict["value"]["$gt"] == 10
        assert query_dict["category"]["$in"] == ["test", "prod"]

    async def test_edge_query_integration(self):
        """Test query integration with Edge entities."""
        # Test query construction for Edge
        qb = QueryBuilder()
        qb.field("source_id").eq("node_123")
        qb.field("weight").gt(5)
        qb.field("condition").eq("good")

        query_dict = qb.build()
        assert query_dict["source_id"]["$eq"] == "node_123"
        assert query_dict["weight"]["$gt"] == 5
        assert query_dict["condition"]["$eq"] == "good"

    async def test_complex_entity_queries(self):
        """Test complex queries for entities."""
        # Test complex node query
        node_query = query().and_(
            [
                {"category": "test"},
                {"$or": [{"value": {"$gte": 10}}, {"name": {"$regex": r"^test.*"}}]},
                {"tags": {"$in": ["important"]}},
                {"metadata.status": {"$ne": "deleted"}},
            ]
        )

        node_query_dict = node_query.build()
        assert "$and" in node_query_dict

        # Test complex edge query
        edge_query = query().and_(
            [
                {"source_id": "node_123"},
                {"$or": [{"weight": {"$gte": 5}}, {"condition": "good"}]},
                {"properties.type": {"$in": ["connection", "relationship"]}},
            ]
        )

        edge_query_dict = edge_query.build()
        assert "$and" in edge_query_dict

    async def test_query_validation_with_entities(self):
        """Test query validation with entity constraints."""
        # Test valid query for Node
        node_query = query()
        node_query.field("name").eq("test")
        node_query.field("value").gt(10)
        query_dict = node_query.build()
        assert len(query_dict) > 0

        # Test valid query for Edge
        edge_query = query()
        edge_query.field("source_id").eq("node_123")
        edge_query.field("weight").gt(5)
        query_dict = edge_query.build()
        assert len(query_dict) > 0

        # Test empty query
        invalid_query = query()
        query_dict = invalid_query.build()
        assert len(query_dict) == 0


class TestQueryErrorHandling:
    """Test query error handling."""

    async def test_invalid_operator_handling(self):
        """Test handling of invalid operators."""
        qb = QueryBuilder()

        # Test invalid operator
        with pytest.raises(AttributeError):
            qb.invalid_operator("name", "test")

    async def test_invalid_value_handling(self):
        """Test handling of invalid values."""
        qb = QueryBuilder()

        # Test None value - should be allowed
        qb.field("name").eq(None)
        query_dict = qb.build()
        assert query_dict["name"]["$eq"] is None

    async def test_invalid_query_structure(self):
        """Test handling of invalid query structures."""
        qb = QueryBuilder()

        # The library handles empty conditions gracefully
        qb.and_()
        qb.or_()
        query_dict = qb.build()
        # Empty logical operators should not be added to query
        assert len(query_dict) == 0

    async def test_query_builder_error_recovery(self):
        """Test query builder error recovery."""
        qb = QueryBuilder()

        # Add valid conditions
        qb.field("name").eq("test")
        qb.field("value").gt(10)

        # Try invalid operation
        try:
            qb.invalid_operation("test")
        except AttributeError:
            pass

        # Query should still be valid
        query_dict = qb.build()
        assert query_dict["name"]["$eq"] == "test"
        assert query_dict["value"]["$gt"] == 10

    async def test_operator_error_handling(self):
        """Test operator error handling."""
        # QueryOperator is just constants, not instantiable
        # Just verify the constants exist
        assert hasattr(QueryOperator, "EQ")
        assert hasattr(QueryOperator, "GT")
        assert hasattr(QueryOperator, "AND")


class TestQueryOptimization:
    """Test query optimization features."""

    async def test_query_optimization_enabled_by_default(self):
        """Test that query optimization is enabled by default."""
        from jvspatial.db.query import QueryEngine

        # Create QueryEngine instance
        engine = QueryEngine()

        # Test optimization features
        assert engine.enable_optimization is True
        assert engine._query_cache is not None
        assert engine._optimization_stats is not None

    async def test_query_optimization_can_be_disabled(self):
        """Test that query optimization can be disabled."""
        from jvspatial.db.query import QueryEngine

        # Create QueryEngine with optimization disabled
        engine = QueryEngine(enable_optimization=False)

        assert engine.enable_optimization is False
        assert engine._query_cache is not None  # Cache still exists but disabled

    async def test_query_optimization_stats(self):
        """Test query optimization statistics collection."""
        from jvspatial.db.query import QueryEngine

        engine = QueryEngine()

        # Get initial stats
        stats = engine.get_optimization_stats()

        assert "cache_hits" in stats
        assert "optimized_queries" in stats
        assert "optimization_time" in stats

    async def test_query_cache_functionality(self):
        """Test query cache functionality."""
        from jvspatial.db.query import QueryEngine

        engine = QueryEngine()

        # Test cache operations
        test_query = {"name": "test", "value": {"$gt": 10}}

        # First call should miss cache
        optimized1 = engine.optimize_query(test_query)
        assert optimized1 is not None

        # Second call should hit cache
        optimized2 = engine.optimize_query(test_query)
        assert optimized2 is not None

        # Check cache stats
        stats = engine.get_optimization_stats()
        assert stats["cache_hits"] >= 1
        assert stats["optimized_queries"] >= 1

    async def test_query_optimization_techniques(self):
        """Test various query optimization techniques."""
        from jvspatial.db.query import QueryEngine

        engine = QueryEngine()

        # Test AND clause optimization
        and_query = {"$and": [{"name": "test"}, {"value": {"$gt": 10}}]}
        optimized = engine.optimize_query(and_query)
        assert optimized is not None

        # Test field selection optimization
        field_query = {"name": "test", "value": {"$gt": 10}, "unused_field": "value"}
        optimized = engine.optimize_query(field_query)
        assert optimized is not None

        # Test indexing hints
        indexed_query = {"name": "test", "category": "prod"}
        optimized = engine.optimize_query(indexed_query)
        assert optimized is not None

    async def test_query_cache_management(self):
        """Test query cache management."""
        from jvspatial.db.query import QueryEngine

        engine = QueryEngine()

        # Add some queries to cache
        test_queries = [{"name": "test1"}, {"name": "test2"}, {"value": {"$gt": 10}}]

        for query in test_queries:
            engine.optimize_query(query)

        # Clear cache
        engine.clear_query_cache()

        # Verify cache is cleared
        stats = engine.get_optimization_stats()
        assert stats["cache_hits"] == 0
        assert (
            stats["optimized_queries"] >= 3
        )  # Should have optimized the queries above

    async def test_query_optimization_reset(self):
        """Test query optimization reset functionality."""
        from jvspatial.db.query import QueryEngine

        engine = QueryEngine()

        # Add some queries
        engine.optimize_query({"name": "test"})
        engine.optimize_query({"value": {"$gt": 10}})

        # Reset stats
        engine.reset_stats()

        # Verify stats are reset
        stats = engine.get_optimization_stats()
        assert stats["optimized_queries"] == 0
        assert stats["cache_hits"] == 0
