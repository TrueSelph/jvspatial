"""Async operation optimization utilities for jvspatial applications.

This module provides comprehensive async operation optimization including
concurrency limiting, batch processing, and performance enhancements.
"""

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

T = TypeVar("T")


class AsyncUtils:
    """Built-in async utilities for common patterns."""

    @staticmethod
    async def gather_with_limit(tasks: List[Awaitable], limit: int) -> List[Any]:
        """Execute tasks with concurrency limit.

        Args:
            tasks: List of awaitable tasks
            limit: Maximum concurrent executions

        Returns:
            List of task results
        """
        semaphore = asyncio.Semaphore(limit)

        async def limited_task(task):
            async with semaphore:
                return await task

        return await asyncio.gather(*[limited_task(task) for task in tasks])

    @staticmethod
    async def timeout_after(seconds: float, coro: Awaitable) -> Any:
        """Execute coroutine with timeout.

        Args:
            seconds: Timeout in seconds
            coro: Coroutine to execute

        Returns:
            Coroutine result

        Raises:
            asyncio.TimeoutError: If operation times out
        """
        try:
            return await asyncio.wait_for(coro, timeout=seconds)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Operation timed out after {seconds} seconds")

    @staticmethod
    async def retry_with_backoff(
        coro: Callable[[], Awaitable[T]],
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff: float = 2.0,
    ) -> T:
        """Execute coroutine with retry and exponential backoff.

        Args:
            coro: Coroutine factory function
            max_attempts: Maximum number of attempts
            delay: Initial delay in seconds
            backoff: Backoff multiplier

        Returns:
            Coroutine result

        Raises:
            Exception: Last exception if all attempts fail
        """
        last_exception = None

        for attempt in range(max_attempts):
            try:
                return await coro()
            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay * (backoff**attempt))

        raise last_exception


class BatchProcessor:
    """Batch processing utility for async operations."""

    def __init__(self, batch_size: int = 10, max_concurrency: int = 5):
        """Initialize batch processor.

        Args:
            batch_size: Number of items per batch
            max_concurrency: Maximum concurrent batches
        """
        self.batch_size = batch_size
        self.max_concurrency = max_concurrency
        self._logger = logging.getLogger(__name__)

    async def process_batches(
        self, items: List[Any], processor: Callable[[List[Any]], Awaitable[List[Any]]]
    ) -> List[Any]:
        """Process items in batches with concurrency control.

        Args:
            items: List of items to process
            processor: Async function to process each batch

        Returns:
            List of processed results
        """
        # Create batches
        batches = [
            items[i : i + self.batch_size]
            for i in range(0, len(items), self.batch_size)
        ]

        # Process batches with concurrency limit
        batch_tasks = [processor(batch) for batch in batches]
        batch_results = await AsyncUtils.gather_with_limit(
            batch_tasks, self.max_concurrency
        )

        # Flatten results
        results = []
        for batch_result in batch_results:
            results.extend(batch_result)

        return results

    async def process_with_progress(
        self,
        items: List[Any],
        processor: Callable[[Any], Awaitable[Any]],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Any]:
        """Process items with progress tracking.

        Args:
            items: List of items to process
            processor: Async function to process each item
            progress_callback: Optional progress callback (current, total)

        Returns:
            List of processed results
        """
        results = []
        total = len(items)

        for i, item in enumerate(items):
            result = await processor(item)
            results.append(result)

            if progress_callback:
                progress_callback(i + 1, total)

        return results


class ConcurrencyLimiter:
    """Concurrency limiting utility for async operations."""

    def __init__(self, limit: int = 10):
        """Initialize concurrency limiter.

        Args:
            limit: Maximum concurrent operations
        """
        self.semaphore = asyncio.Semaphore(limit)
        self._active_count = 0
        self._logger = logging.getLogger(__name__)

    async def execute(self, coro: Awaitable[T]) -> T:
        """Execute coroutine with concurrency limit.

        Args:
            coro: Coroutine to execute

        Returns:
            Coroutine result
        """
        async with self.semaphore:
            self._active_count += 1
            try:
                return await coro
            finally:
                self._active_count -= 1

    def get_active_count(self) -> int:
        """Get current number of active operations.

        Returns:
            Number of active operations
        """
        return self._active_count

    def get_available_slots(self) -> int:
        """Get number of available concurrency slots.

        Returns:
            Number of available slots
        """
        return self.semaphore._value


class AsyncCache:
    """Async-aware cache with TTL and size limits."""

    def __init__(self, max_size: int = 1000, default_ttl: float = 300.0):
        """Initialize async cache.

        Args:
            max_size: Maximum cache size
            default_ttl: Default TTL in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_order: List[str] = []
        self._logger = logging.getLogger(__name__)

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if key not in self._cache:
            return None

        entry = self._cache[key]

        # Check TTL
        if time.time() > entry["expires_at"]:
            await self.delete(key)
            return None

        # Update access order
        self._access_order.remove(key)
        self._access_order.append(key)

        return entry["value"]

    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL override
        """
        if ttl is None:
            ttl = self.default_ttl

        expires_at = time.time() + ttl

        # Remove existing entry if present
        if key in self._cache:
            self._access_order.remove(key)

        # Add new entry
        self._cache[key] = {"value": value, "expires_at": expires_at}
        self._access_order.append(key)

        # Enforce size limit
        await self._enforce_size_limit()

    async def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if not found
        """
        if key not in self._cache:
            return False

        del self._cache[key]
        self._access_order.remove(key)
        return True

    async def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._access_order.clear()

    async def _enforce_size_limit(self) -> None:
        """Enforce cache size limit by removing oldest entries."""
        while len(self._cache) > self.max_size:
            oldest_key = self._access_order.pop(0)
            del self._cache[oldest_key]


class AsyncOptimizer:
    """Comprehensive async operation optimizer."""

    def __init__(self, default_concurrency_limit: int = 10):
        """Initialize async optimizer.

        Args:
            default_concurrency_limit: Default concurrency limit
        """
        self.default_concurrency_limit = default_concurrency_limit
        self.batch_processor = BatchProcessor()
        self.concurrency_limiter = ConcurrencyLimiter(default_concurrency_limit)
        self.async_cache = AsyncCache()
        self._logger = logging.getLogger(__name__)

    async def optimize_operation(
        self,
        operation: Callable[[], Awaitable[T]],
        use_cache: bool = False,
        cache_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> T:
        """Optimize a single async operation.

        Args:
            operation: Async operation to optimize
            use_cache: Whether to use caching
            cache_key: Optional cache key
            timeout: Optional timeout in seconds

        Returns:
            Operation result
        """
        # Check cache first
        if use_cache and cache_key:
            cached_result = await self.async_cache.get(cache_key)
            if cached_result is not None:
                return cached_result

        # Execute operation with optimizations
        async def optimized_operation():
            if timeout:
                return await AsyncUtils.timeout_after(timeout, operation())
            else:
                return await operation()

        result = await self.concurrency_limiter.execute(optimized_operation())

        # Cache result if requested
        if use_cache and cache_key:
            await self.async_cache.set(cache_key, result)

        return result

    async def optimize_batch_operations(
        self,
        items: List[Any],
        processor: Callable[[Any], Awaitable[Any]],
        batch_size: int = 10,
        max_concurrency: int = 5,
    ) -> List[Any]:
        """Optimize batch operations.

        Args:
            items: List of items to process
            processor: Async processor function
            batch_size: Batch size
            max_concurrency: Maximum concurrent batches

        Returns:
            List of processed results
        """
        # Create batch processor with custom settings
        batch_processor = BatchProcessor(batch_size, max_concurrency)

        # Process items in batches
        async def process_batch(batch_items):
            return await AsyncUtils.gather_with_limit(
                [processor(item) for item in batch_items], max_concurrency
            )

        return await batch_processor.process_batches(items, process_batch)

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get optimization statistics.

        Returns:
            Optimization statistics dictionary
        """
        return {
            "active_operations": self.concurrency_limiter.get_active_count(),
            "available_slots": self.concurrency_limiter.get_available_slots(),
            "cache_size": len(self.async_cache._cache),
            "cache_max_size": self.async_cache.max_size,
        }


# Global async optimizer instance
async_optimizer = AsyncOptimizer()


# Convenience functions
async def gather_with_limit(tasks: List[Awaitable], limit: int) -> List[Any]:
    """Execute tasks with concurrency limit.

    Args:
        tasks: List of awaitable tasks
        limit: Maximum concurrent executions

    Returns:
        List of task results
    """
    return await AsyncUtils.gather_with_limit(tasks, limit)


async def timeout_after(seconds: float, coro: Awaitable) -> Any:
    """Execute coroutine with timeout.

    Args:
        seconds: Timeout in seconds
        coro: Coroutine to execute

    Returns:
        Coroutine result
    """
    return await AsyncUtils.timeout_after(seconds, coro)


async def retry_with_backoff(
    coro: Callable[[], Awaitable[T]],
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
) -> T:
    """Execute coroutine with retry and exponential backoff.

    Args:
        coro: Coroutine factory function
        max_attempts: Maximum number of attempts
        delay: Initial delay in seconds
        backoff: Backoff multiplier

    Returns:
        Coroutine result
    """
    return await AsyncUtils.retry_with_backoff(coro, max_attempts, delay, backoff)


# Decorators
def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Retry decorator for async functions.

    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay in seconds
        backoff: Backoff multiplier

    Returns:
        Decorator function
    """

    def decorator(func):
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await AsyncUtils.retry_with_backoff(
                lambda: func(*args, **kwargs), max_attempts, delay, backoff
            )

        return wrapper

    return decorator


def timeout(seconds: float):
    """Timeout decorator for async functions.

    Args:
        seconds: Timeout in seconds

    Returns:
        Decorator function
    """

    def decorator(func):
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await AsyncUtils.timeout_after(seconds, func(*args, **kwargs))

        return wrapper

    return decorator


__all__ = [
    "AsyncUtils",
    "BatchProcessor",
    "ConcurrencyLimiter",
    "AsyncCache",
    "AsyncOptimizer",
    "async_optimizer",
    "gather_with_limit",
    "timeout_after",
    "retry_with_backoff",
    "retry",
    "timeout",
]
