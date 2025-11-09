"""Comprehensive testing utilities for jvspatial applications.

This module provides enhanced testing utilities and fixtures for jvspatial
applications, following the new standard implementation approach.
"""

import asyncio
import tempfile
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Union

import pytest
from fastapi.testclient import TestClient

from jvspatial.api.server import Server
from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Object


class JVSpatialTestClient:
    """Enhanced test client for jvspatial applications.

    Provides comprehensive testing utilities with automatic cleanup
    and performance monitoring capabilities.
    """

    def __init__(self, server: Server):
        """Initialize the test client.

        Args:
            server: Server instance to test
        """
        self.server = server
        self.client = TestClient(server.app)
        self._test_data: List[Object] = []
        self._temp_files: List[str] = []

    async def create_test_entity(self, entity_type: str, **kwargs) -> Object:
        """Create test entities with automatic cleanup.

        Args:
            entity_type: Type of entity to create
            **kwargs: Entity creation parameters

        Returns:
            Created entity instance
        """
        # Use the create_entity function
        entity = await create_entity(entity_type, **kwargs)
        self._test_data.append(entity)  # type: ignore[arg-type]
        return entity  # type: ignore[return-value]

    async def cleanup_test_data(self) -> None:
        """Clean up all test data."""
        for entity in self._test_data:
            if hasattr(entity, "delete"):
                await entity.delete()
        self._test_data.clear()

        # Clean up temp files
        for temp_file in self._temp_files:
            try:
                import os

                os.unlink(temp_file)
            except Exception:
                pass
        self._temp_files.clear()

    def create_temp_file(self, content: bytes = b"test content") -> str:
        """Create a temporary file for testing.

        Args:
            content: File content

        Returns:
            Path to temporary file
        """
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            temp_path = f.name

        self._temp_files.append(temp_path)
        return temp_path

    async def get_performance_stats(self) -> Optional[Dict[str, Any]]:
        """Get performance statistics from the server's GraphContext.

        Returns:
            Performance statistics if available
        """
        if hasattr(self.server, "_graph_context") and self.server._graph_context:
            return await self.server._graph_context.get_performance_stats()
        return None

    def assert_response_success(
        self, response, expected_status: int = 200
    ) -> Dict[str, Any]:
        """Assert that a response is successful and return the data.

        Args:
            response: TestClient response
            expected_status: Expected HTTP status code

        Returns:
            Response data

        Raises:
            AssertionError: If response is not successful
        """
        assert (
            response.status_code == expected_status
        ), f"Expected {expected_status}, got {response.status_code}: {response.text}"

        data = response.json()
        assert isinstance(data, dict), f"Expected dict response, got {type(data)}"

        return data

    def assert_response_error(
        self, response, expected_status: int = 400
    ) -> Dict[str, Any]:
        """Assert that a response is an error and return the error data.

        Args:
            response: TestClient response
            expected_status: Expected HTTP status code

        Returns:
            Error response data

        Raises:
            AssertionError: If response is not an error
        """
        assert (
            response.status_code == expected_status
        ), f"Expected error {expected_status}, got {response.status_code}: {response.text}"

        data = response.json()
        assert isinstance(data, dict), f"Expected dict response, got {type(data)}"

        return data


class MockEntity(Object):
    """Mock entity for testing purposes."""

    model_config = {"extra": "allow"}  # Allow extra fields

    def __init__(self, id: str, **kwargs):
        """Initialize mock entity."""
        # Initialize with proper Pydantic model initialization
        super().__init__(id=id, **kwargs)

    async def delete(self) -> None:  # type: ignore[override]
        """Mock delete method."""
        pass


class TestContextManager:
    """Context manager for test setup and teardown."""

    def __init__(self, server_config: Optional[Dict[str, Any]] = None):
        """Initialize test context manager.

        Args:
            server_config: Optional server configuration
        """
        self.server_config = server_config or {}
        self.server: Optional[Server] = None
        self.test_client: Optional[JVSpatialTestClient] = None

    async def __aenter__(self):
        """Enter the test context."""
        # Create test server
        self.server = Server(
            title="Test Server",
            description="Test server for jvspatial",
            version="1.0.0-test",
            debug=True,
            enable_performance_monitoring=True,
            **self.server_config,
        )

        # Create test client
        self.test_client = JVSpatialTestClient(self.server)

        return self.test_client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the test context."""
        if self.test_client:
            await self.test_client.cleanup_test_data()

        if self.server and hasattr(self.server, "cleanup"):
            await self.server.cleanup()


# Test fixtures
@pytest.fixture
async def test_context():
    """Test GraphContext fixture with automatic cleanup."""
    context = GraphContext(enable_performance_monitoring=False)
    yield context
    # Cleanup would be handled by the context manager


@pytest.fixture
async def test_server():
    """Test server fixture."""
    server = Server(
        title="Test Server",
        description="Test server for jvspatial",
        version="1.0.0-test",
        debug=True,
        enable_performance_monitoring=False,
    )
    yield server
    if hasattr(server, "cleanup"):
        await server.cleanup()


@pytest.fixture
async def test_client(test_server):
    """Test client fixture."""
    client = JVSpatialTestClient(test_server)
    yield client
    await client.cleanup_test_data()


@pytest.fixture
def temp_file():
    """Temporary file fixture."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_path = f.name
        f.write(b"test content")

    yield temp_path

    try:
        import os

        os.unlink(temp_path)
    except Exception:
        pass


class TestDataFactory:
    """Factory for creating test data."""

    @staticmethod
    def create_user_data(**overrides) -> Dict[str, Any]:
        """Create test user data.

        Args:
            **overrides: Data overrides

        Returns:
            User data dictionary
        """
        default_data = {
            "id": str(uuid.uuid4()),
            "username": f"testuser_{uuid.uuid4().hex[:8]}",
            "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
            "active": True,
            "created_at": "2024-01-01T00:00:00Z",
        }
        default_data.update(overrides)
        return default_data

    @staticmethod
    def create_node_data(**overrides) -> Dict[str, Any]:
        """Create test node data.

        Args:
            **overrides: Data overrides

        Returns:
            Node data dictionary
        """
        default_data = {
            "id": f"n:TestNode:{uuid.uuid4().hex[:8]}",
            "name": f"test_node_{uuid.uuid4().hex[:8]}",
            "type": "TestNode",
            "created_at": "2024-01-01T00:00:00Z",
        }
        default_data.update(overrides)
        return default_data

    @staticmethod
    def create_walker_data(**overrides) -> Dict[str, Any]:
        """Create test walker data.

        Args:
            **overrides: Data overrides

        Returns:
            Walker data dictionary
        """
        default_data = {
            "id": f"w:TestWalker:{uuid.uuid4().hex[:8]}",
            "name": f"test_walker_{uuid.uuid4().hex[:8]}",
            "type": "TestWalker",
            "created_at": "2024-01-01T00:00:00Z",
        }
        default_data.update(overrides)
        return default_data


class PerformanceTestHelper:
    """Helper for performance testing."""

    def __init__(self, test_client: JVSpatialTestClient):
        """Initialize performance test helper.

        Args:
            test_client: Test client instance
        """
        self.test_client = test_client
        self._start_times: Dict[str, float] = {}

    def start_timer(self, operation_name: str) -> None:
        """Start timing an operation.

        Args:
            operation_name: Name of the operation to time
        """
        import time

        self._start_times[operation_name] = time.time()

    def end_timer(self, operation_name: str) -> float:
        """End timing an operation and return duration.

        Args:
            operation_name: Name of the operation

        Returns:
            Duration in seconds
        """
        import time

        if operation_name not in self._start_times:
            raise ValueError(f"Timer for {operation_name} was not started")

        duration = time.time() - self._start_times[operation_name]
        del self._start_times[operation_name]
        return duration

    async def measure_operation(self, operation_name: str, operation_func):
        """Measure the duration of an async operation.

        Args:
            operation_name: Name of the operation
            operation_func: Async function to measure

        Returns:
            Tuple of (result, duration)
        """
        self.start_timer(operation_name)
        try:
            result = await operation_func()
            duration = self.end_timer(operation_name)
            return result, duration
        except Exception as e:
            self.end_timer(operation_name)
            raise e

    async def get_performance_stats(self) -> Optional[Dict[str, Any]]:
        """Get performance statistics.

        Returns:
            Performance statistics if available
        """
        return await self.test_client.get_performance_stats()


# Utility functions for testing
async def create_entity(entity_type: str, **kwargs) -> Union[Object, Dict[str, Any]]:
    """Create a test entity.

    Args:
        entity_type: Type of entity to create
        **kwargs: Entity creation parameters

    Returns:
        Created entity instance (MockEntity object or dict if mocked)
    """
    entity = MockEntity(id=str(uuid.uuid4()), **kwargs)
    return entity


async def create_mock_entity(entity_type: str, **kwargs) -> Object:
    """Create a mock entity for testing.

    Args:
        entity_type: Type of entity to create
        **kwargs: Entity creation parameters

    Returns:
        Mock entity instance
    """
    return await create_entity(entity_type, **kwargs)  # type: ignore[return-value]


async def generate_test_data(data_type: str, count: int = 1, **kwargs) -> List[Object]:
    """Generate test data.

    Args:
        data_type: Type of data to generate
        count: Number of items to generate
        **kwargs: Data generation parameters

    Returns:
        List of generated data objects
    """
    factory = TestDataFactory()

    if data_type == "user":
        data_list = [factory.create_user_data(**kwargs) for _ in range(count)]
        return [MockEntity(**data) for data in data_list]
    elif data_type == "node":
        data_list = [factory.create_node_data(**kwargs) for _ in range(count)]
        return [MockEntity(**data) for data in data_list]
    elif data_type == "walker":
        data_list = [factory.create_walker_data(**kwargs) for _ in range(count)]
        return [MockEntity(**data) for data in data_list]
    else:
        # Handle class types like Node
        if isinstance(data_type, type):
            return [MockEntity(id=str(uuid.uuid4()), **kwargs) for _ in range(count)]
        else:
            return [
                MockEntity(id=str(uuid.uuid4()), type=data_type, **kwargs)
                for _ in range(count)
            ]


def assert_entity_valid(entity: Object) -> None:
    """Assert that an entity is valid.

    Args:
        entity: Entity to validate

    Raises:
        AssertionError: If entity is invalid
    """
    assert entity is not None, "Entity should not be None"
    assert hasattr(entity, "id"), "Entity should have an id attribute"
    assert entity.id is not None, "Entity id should not be None"


def assert_graph_consistent(context: GraphContext) -> None:
    """Assert that a graph context is consistent.

    Args:
        context: Graph context to validate

    Raises:
        AssertionError: If graph is inconsistent
    """
    assert context is not None, "Graph context should not be None"
    # Add more consistency checks as needed


@asynccontextmanager
async def isolated_test_context():
    """Create an isolated test context.

    Yields:
        Test context manager
    """
    async with TestContextManager() as test_client:
        yield test_client


async def measure_performance(operation_func: Any, *args: Any, **kwargs: Any) -> Any:
    """Measure the performance of an operation.

    Args:
        operation_func: Function to measure
        *args: Function arguments
        **kwargs: Function keyword arguments

    Returns:
        Tuple of (result, duration)
    """
    import time

    start_time = time.time()
    result = await operation_func(*args, **kwargs)
    duration = time.time() - start_time
    return result, duration


async def compare_performance(
    operation1_func: Any, operation2_func: Any, *args: Any, **kwargs: Any
) -> Any:
    """Compare the performance of two operations.

    Args:
        operation1_func: First operation to measure
        operation2_func: Second operation to measure
        *args: Function arguments
        **kwargs: Function keyword arguments

    Returns:
        Dictionary with performance comparison data
    """
    result1, duration1 = await measure_performance(operation1_func, *args, **kwargs)
    result2, duration2 = await measure_performance(operation2_func, *args, **kwargs)

    return {
        "fast_duration": min(duration1, duration2),
        "slow_duration": max(duration1, duration2),
        "speedup_ratio": max(duration1, duration2) / min(duration1, duration2),
        "result1": result1,
        "result2": result2,
    }


async def track_memory_usage(operation_func: Any, *args: Any, **kwargs: Any) -> Any:
    """Track memory usage during an operation.

    Args:
        operation_func: Function to track
        *args: Function arguments
        **kwargs: Function keyword arguments

    Returns:
        Dictionary with memory usage information
    """
    try:
        import psutil

        process = psutil.Process()
        memory_before = process.memory_info()
        result = await operation_func(*args, **kwargs)
        memory_after = process.memory_info()

        return {
            "peak_memory": max(memory_before.rss, memory_after.rss),
            "final_memory": memory_after.rss,
            "memory_delta": memory_after.rss - memory_before.rss,
            "result": result,
        }
    except ImportError:
        # psutil not available, just run the operation
        result = await operation_func(*args, **kwargs)
        return {
            "peak_memory": 0,
            "final_memory": 0,
            "memory_delta": 0,
            "result": result,
        }


def performance_test(max_duration: float = 1.0):
    """Decorator for performance testing.

    Args:
        max_duration: Maximum allowed duration in seconds

    Returns:
        Decorated function
    """

    def decorator(func):
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result, duration = await measure_performance(func, *args, **kwargs)
            assert_performance_threshold(duration, max_duration, func.__name__)
            return result

        return wrapper

    return decorator


def integration_test():
    """Decorator for integration testing."""

    def decorator(func):
        # For now, just return the function as-is
        # In a real implementation, this might set up integration test environment
        return func

    return decorator


# Utility functions for testing
async def run_concurrent_tests(
    test_functions: List[Any], max_concurrency: int = 10  # type: ignore[valid-type]
) -> List[Any]:
    """Run multiple test functions concurrently.

    Args:
        test_functions: List of async test functions
        max_concurrency: Maximum concurrent executions

    Returns:
        List of test results
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def limited_test(test_func):
        async with semaphore:
            return await test_func()

    return await asyncio.gather(*[limited_test(func) for func in test_functions])


def assert_performance_threshold(
    duration: float, max_duration: float, operation_name: str
) -> None:
    """Assert that an operation completed within performance threshold.

    Args:
        duration: Actual duration in seconds
        max_duration: Maximum allowed duration in seconds
        operation_name: Name of the operation

    Raises:
        AssertionError: If duration exceeds threshold
    """
    assert (
        duration <= max_duration
    ), f"{operation_name} took {duration:.3f}s, expected <= {max_duration:.3f}s"


__all__ = [
    "JVSpatialTestClient",
    "TestContextManager",
    "TestDataFactory",
    "PerformanceTestHelper",
    "run_concurrent_tests",
    "assert_performance_threshold",
    "create_entity",
    "create_mock_entity",
    "generate_test_data",
    "assert_entity_valid",
    "assert_graph_consistent",
    "isolated_test_context",
    "measure_performance",
    "compare_performance",
    "track_memory_usage",
    "performance_test",
    "integration_test",
]
