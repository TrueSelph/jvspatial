"""Performance profiling tools for jvspatial applications.

This module provides comprehensive performance profiling and monitoring
tools for jvspatial applications, following the new standard implementation.
"""

import asyncio
import cProfile
import functools
import logging
import pstats
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Dict, List, Optional

from jvspatial.logging import performance_logger


class PerformanceProfiler:
    """Comprehensive performance profiler for jvspatial applications.

    Provides detailed performance profiling with timing, memory usage,
    and database operation tracking.
    """

    def __init__(self, enable_detailed_profiling: bool = True):
        """Initialize the performance profiler.

        Args:
            enable_detailed_profiling: Whether to enable detailed profiling
        """
        self.enable_detailed_profiling = enable_detailed_profiling
        self._profiler = cProfile.Profile() if enable_detailed_profiling else None
        self._operation_times: Dict[str, List[float]] = {}
        self._memory_usage: List[Dict[str, Any]] = []
        self._logger = logging.getLogger(__name__)

    @contextmanager
    def profile_operation(self, operation_name: str):
        """Context manager for profiling operations.

        Args:
            operation_name: Name of the operation to profile

        Yields:
            Profiler context
        """
        start_time = time.time()
        start_memory = self._get_memory_usage()

        if self._profiler:
            self._profiler.enable()

        try:
            yield self
        finally:
            if self._profiler:
                self._profiler.disable()

            end_time = time.time()
            end_memory = self._get_memory_usage()
            duration = end_time - start_time

            # Record operation time
            if operation_name not in self._operation_times:
                self._operation_times[operation_name] = []
            self._operation_times[operation_name].append(duration)

            # Record memory usage
            self._memory_usage.append(
                {
                    "operation": operation_name,
                    "start_memory": start_memory,
                    "end_memory": end_memory,
                    "memory_delta": end_memory - start_memory,
                    "timestamp": time.time(),
                }
            )

            # Log performance metrics
            performance_logger.log_operation(
                operation_name,
                duration,
                start_memory=start_memory,
                end_memory=end_memory,
                memory_delta=end_memory - start_memory,
            )

    @asynccontextmanager
    async def profile_async_operation(self, operation_name: str):
        """Async context manager for profiling async operations.

        Args:
            operation_name: Name of the operation to profile

        Yields:
            Profiler context
        """
        start_time = time.time()
        start_memory = self._get_memory_usage()

        if self._profiler:
            self._profiler.enable()

        try:
            yield self
        finally:
            if self._profiler:
                self._profiler.disable()

            end_time = time.time()
            end_memory = self._get_memory_usage()
            duration = end_time - start_time

            # Record operation time
            if operation_name not in self._operation_times:
                self._operation_times[operation_name] = []
            self._operation_times[operation_name].append(duration)

            # Record memory usage
            self._memory_usage.append(
                {
                    "operation": operation_name,
                    "start_memory": start_memory,
                    "end_memory": end_memory,
                    "memory_delta": end_memory - start_memory,
                    "timestamp": time.time(),
                }
            )

            # Log performance metrics
            performance_logger.log_operation(
                operation_name,
                duration,
                start_memory=start_memory,
                end_memory=end_memory,
                memory_delta=end_memory - start_memory,
            )

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB.

        Returns:
            Memory usage in megabytes
        """
        try:
            import psutil

            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            return 0.0

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics.

        Returns:
            Performance statistics dictionary
        """
        stats = {
            "operation_times": {},
            "memory_usage": self._memory_usage,
            "total_operations": len(self._operation_times),
        }

        # Calculate operation statistics
        for operation_name, times in self._operation_times.items():
            if times:
                stats["operation_times"][operation_name] = {
                    "count": len(times),
                    "total_time": sum(times),
                    "average_time": sum(times) / len(times),
                    "min_time": min(times),
                    "max_time": max(times),
                }

        return stats

    def get_profiler_stats(self) -> Optional[pstats.Stats]:
        """Get detailed profiler statistics.

        Returns:
            Profiler statistics if available, None otherwise
        """
        if self._profiler:
            return pstats.Stats(self._profiler)
        return None

    def reset_stats(self) -> None:
        """Reset all performance statistics."""
        self._operation_times.clear()
        self._memory_usage.clear()
        if self._profiler:
            self._profiler.clear()


class DatabaseProfiler:
    """Specialized profiler for database operations."""

    def __init__(self):
        """Initialize the database profiler."""
        self._query_times: Dict[str, List[float]] = {}
        self._query_counts: Dict[str, int] = {}
        self._logger = logging.getLogger(__name__)

    def profile_query(self, query_type: str, collection: str):
        """Context manager for profiling database queries.

        Args:
            query_type: Type of query (select, insert, update, delete)
            collection: Collection name

        Yields:
            Profiler context
        """
        start_time = time.time()

        try:
            yield
        finally:
            duration = time.time() - start_time

            # Record query performance
            query_key = f"{query_type}:{collection}"
            if query_key not in self._query_times:
                self._query_times[query_key] = []
            self._query_times[query_key].append(duration)

            if query_key not in self._query_counts:
                self._query_counts[query_key] = 0
            self._query_counts[query_key] += 1

            # Log database operation
            performance_logger.log_database_operation(query_type, collection, duration)

    def get_query_stats(self) -> Dict[str, Any]:
        """Get database query statistics.

        Returns:
            Query statistics dictionary
        """
        stats = {"queries": {}, "total_queries": sum(self._query_counts.values())}

        for query_key, times in self._query_times.items():
            if times:
                stats["queries"][query_key] = {
                    "count": len(times),
                    "total_time": sum(times),
                    "average_time": sum(times) / len(times),
                    "min_time": min(times),
                    "max_time": max(times),
                }

        return stats


class CacheProfiler:
    """Specialized profiler for cache operations."""

    def __init__(self):
        """Initialize the cache profiler."""
        self._cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "hit_times": [],
            "miss_times": [],
            "set_times": [],
            "delete_times": [],
        }
        self._logger = logging.getLogger(__name__)

    def profile_cache_operation(self, operation: str, key: str):
        """Context manager for profiling cache operations.

        Args:
            operation: Cache operation type (get, set, delete)
            key: Cache key

        Yields:
            Profiler context
        """
        start_time = time.time()
        hit = False

        try:
            yield hit
        finally:
            duration = time.time() - start_time

            # Record operation statistics
            if operation == "get":
                if hit:
                    self._cache_stats["hits"] += 1
                    self._cache_stats["hit_times"].append(duration)
                else:
                    self._cache_stats["misses"] += 1
                    self._cache_stats["miss_times"].append(duration)
            elif operation == "set":
                self._cache_stats["sets"] += 1
                self._cache_stats["set_times"].append(duration)
            elif operation == "delete":
                self._cache_stats["deletes"] += 1
                self._cache_stats["delete_times"].append(duration)

            # Log cache operation
            performance_logger.log_cache_operation(operation, key, hit, duration)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics.

        Returns:
            Cache statistics dictionary
        """
        total_operations = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = (
            (self._cache_stats["hits"] / total_operations * 100)
            if total_operations > 0
            else 0
        )

        stats = {
            "hit_rate": hit_rate,
            "total_operations": total_operations,
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "sets": self._cache_stats["sets"],
            "deletes": self._cache_stats["deletes"],
        }

        # Add timing statistics
        for operation in ["hit", "miss", "set", "delete"]:
            times_key = f"{operation}_times"
            if self._cache_stats[times_key]:
                stats[f"{operation}_timing"] = {
                    "average": sum(self._cache_stats[times_key])
                    / len(self._cache_stats[times_key]),
                    "min": min(self._cache_stats[times_key]),
                    "max": max(self._cache_stats[times_key]),
                }

        return stats


class PerformanceDecorator:
    """Decorator for automatic performance profiling."""

    def __init__(self, profiler: PerformanceProfiler):
        """Initialize the performance decorator.

        Args:
            profiler: Performance profiler instance
        """
        self.profiler = profiler

    def profile_function(self, operation_name: Optional[str] = None):
        """Decorator for profiling functions.

        Args:
            operation_name: Optional operation name (defaults to function name)

        Returns:
            Decorated function
        """

        def decorator(func):
            name = operation_name or f"{func.__module__}.{func.__name__}"

            if asyncio.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    with self.profiler.profile_operation(name):
                        return await func(*args, **kwargs)

                return async_wrapper
            else:

                @functools.wraps(func)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    with self.profiler.profile_operation(name):
                        return func(*args, **kwargs)

                return sync_wrapper

        return decorator


class PerformanceMonitor:
    """Comprehensive performance monitoring system."""

    def __init__(self, enable_profiling: bool = True):
        """Initialize the performance monitor.

        Args:
            enable_profiling: Whether to enable detailed profiling
        """
        self.profiler = PerformanceProfiler(enable_profiling)
        self.db_profiler = DatabaseProfiler()
        self.cache_profiler = CacheProfiler()
        self.decorator = PerformanceDecorator(self.profiler)
        self._logger = logging.getLogger(__name__)

    def profile(self, operation_name: Optional[str] = None):
        """Decorator for profiling functions.

        Args:
            operation_name: Optional operation name

        Returns:
            Decorator function
        """
        return self.decorator.profile_function(operation_name)

    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics.

        Returns:
            Comprehensive statistics dictionary
        """
        return {
            "general": self.profiler.get_performance_stats(),
            "database": self.db_profiler.get_query_stats(),
            "cache": self.cache_profiler.get_cache_stats(),
        }

    def reset_all_stats(self) -> None:
        """Reset all performance statistics."""
        self.profiler.reset_stats()
        self.db_profiler._query_times.clear()
        self.db_profiler._query_counts.clear()
        self.cache_profiler._cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "hit_times": [],
            "miss_times": [],
            "set_times": [],
            "delete_times": [],
        }


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


# Convenience functions
def profile_function(operation_name: Optional[str] = None):
    """Convenience decorator for profiling functions.

    Args:
        operation_name: Optional operation name

    Returns:
        Decorator function
    """
    return performance_monitor.profile(operation_name)


def get_performance_stats() -> Dict[str, Any]:
    """Get comprehensive performance statistics.

    Returns:
        Performance statistics dictionary
    """
    return performance_monitor.get_comprehensive_stats()


def reset_performance_stats() -> None:
    """Reset all performance statistics."""
    performance_monitor.reset_all_stats()


__all__ = [
    "PerformanceProfiler",
    "DatabaseProfiler",
    "CacheProfiler",
    "PerformanceDecorator",
    "PerformanceMonitor",
    "performance_monitor",
    "profile_function",
    "get_performance_stats",
    "reset_performance_stats",
]
