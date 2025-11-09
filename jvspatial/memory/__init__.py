"""Memory management enhancements for jvspatial applications.

This module provides comprehensive memory management capabilities including
memory monitoring, automatic cleanup, and optimization strategies.
"""

import asyncio
import gc
import logging
import time
from typing import Any, Dict, List, Optional
from weakref import WeakSet

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class MemoryMonitor:
    """Memory usage monitoring and tracking system."""

    def __init__(self, enable_monitoring: bool = True):
        """Initialize memory monitor.

        Args:
            enable_monitoring: Whether to enable memory monitoring
        """
        self.enable_monitoring = enable_monitoring
        self._logger = logging.getLogger(__name__)
        self._memory_samples: List[Dict[str, Any]] = []
        self._max_samples = 1000

        if not PSUTIL_AVAILABLE:
            self._logger.warning("psutil not available, memory monitoring disabled")
            self.enable_monitoring = False

    def get_memory_usage(self) -> Dict[str, Any]:
        """Get current memory usage statistics.

        Returns:
            Memory usage dictionary
        """
        if not self.enable_monitoring or not PSUTIL_AVAILABLE:
            return {"error": "Memory monitoring not available"}

        try:
            process = psutil.Process()
            memory_info = process.memory_info()

            stats = {
                "rss_mb": memory_info.rss / 1024 / 1024,  # Resident Set Size
                "vms_mb": memory_info.vms / 1024 / 1024,  # Virtual Memory Size
                "percent": process.memory_percent(),
                "available_mb": psutil.virtual_memory().available / 1024 / 1024,
                "timestamp": time.time(),
            }

            # Record sample
            self._memory_samples.append(stats)
            if len(self._memory_samples) > self._max_samples:
                self._memory_samples.pop(0)

            return stats

        except Exception as e:
            self._logger.error(f"Failed to get memory usage: {e}")
            return {"error": str(e)}

    def get_memory_trend(self) -> Dict[str, Any]:
        """Get memory usage trend over time.

        Returns:
            Memory trend analysis
        """
        if len(self._memory_samples) < 2:
            return {"error": "Insufficient data for trend analysis"}

        recent_samples = self._memory_samples[-10:]  # Last 10 samples

        rss_values = [s["rss_mb"] for s in recent_samples]
        # timestamps = [s["timestamp"] for s in recent_samples]  # Unused for now

        # Calculate trend
        if len(rss_values) >= 2:
            trend = (rss_values[-1] - rss_values[0]) / len(rss_values)
        else:
            trend = 0

        return {
            "current_mb": rss_values[-1],
            "average_mb": sum(rss_values) / len(rss_values),
            "min_mb": min(rss_values),
            "max_mb": max(rss_values),
            "trend_mb_per_sample": trend,
            "sample_count": len(recent_samples),
        }

    def is_memory_pressure(self, threshold_mb: float = 500) -> bool:
        """Check if memory usage is above threshold.

        Args:
            threshold_mb: Memory threshold in MB

        Returns:
            True if memory pressure detected
        """
        usage = self.get_memory_usage()
        if "error" in usage:
            return False

        return usage["rss_mb"] > threshold_mb


class MemoryCleanup:
    """Automatic memory cleanup and optimization system."""

    def __init__(self, max_memory_mb: int = 512, cleanup_threshold: float = 0.8):
        """Initialize memory cleanup system.

        Args:
            max_memory_mb: Maximum memory usage in MB
            cleanup_threshold: Threshold for triggering cleanup (0.0-1.0)
        """
        self.max_memory = max_memory_mb * 1024 * 1024  # Convert to bytes
        self.cleanup_threshold = cleanup_threshold
        self._logger = logging.getLogger(__name__)
        self._cleanup_callbacks: List[callable] = []
        self._weak_refs: WeakSet = WeakSet()

    def register_cleanup_callback(self, callback: callable) -> None:
        """Register a cleanup callback.

        Args:
            callback: Function to call during cleanup
        """
        self._cleanup_callbacks.append(callback)

    def register_weak_ref(self, obj: Any) -> None:
        """Register an object for weak reference tracking.

        Args:
            obj: Object to track
        """
        self._weak_refs.add(obj)

    async def check_and_cleanup(self) -> Dict[str, Any]:
        """Check memory usage and perform cleanup if needed.

        Returns:
            Cleanup results dictionary
        """
        if not PSUTIL_AVAILABLE:
            return {"error": "Memory monitoring not available"}

        try:
            process = psutil.Process()
            current_memory = process.memory_info().rss

            memory_ratio = current_memory / self.max_memory

            if memory_ratio > self.cleanup_threshold:
                return await self._perform_cleanup()
            else:
                return {
                    "cleanup_performed": False,
                    "memory_ratio": memory_ratio,
                    "current_memory_mb": current_memory / 1024 / 1024,
                }

        except Exception as e:
            self._logger.error(f"Memory cleanup check failed: {e}")
            return {"error": str(e)}

    async def _perform_cleanup(self) -> Dict[str, Any]:
        """Perform memory cleanup operations.

        Returns:
            Cleanup results dictionary
        """
        cleanup_results = {
            "cleanup_performed": True,
            "operations": [],
            "memory_before_mb": 0,
            "memory_after_mb": 0,
        }

        try:
            process = psutil.Process()
            memory_before = process.memory_info().rss
            cleanup_results["memory_before_mb"] = memory_before / 1024 / 1024

            # Run garbage collection
            collected = gc.collect()
            cleanup_results["operations"].append(
                f"Garbage collection: {collected} objects"
            )

            # Run registered cleanup callbacks
            for callback in self._cleanup_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                    cleanup_results["operations"].append(
                        f"Callback: {callback.__name__}"
                    )
                except Exception as e:
                    self._logger.warning(f"Cleanup callback failed: {e}")

            # Clear weak references
            initial_count = len(self._weak_refs)
            self._weak_refs.clear()
            cleanup_results["operations"].append(
                f"Cleared {initial_count} weak references"
            )

            # Force garbage collection again
            collected = gc.collect()
            cleanup_results["operations"].append(
                f"Final garbage collection: {collected} objects"
            )

            memory_after = process.memory_info().rss
            cleanup_results["memory_after_mb"] = memory_after / 1024 / 1024
            cleanup_results["memory_freed_mb"] = (
                (memory_before - memory_after) / 1024 / 1024
            )

            self._logger.info(
                f"Memory cleanup completed: freed {cleanup_results['memory_freed_mb']:.2f} MB"
            )

        except Exception as e:
            self._logger.error(f"Memory cleanup failed: {e}")
            cleanup_results["error"] = str(e)

        return cleanup_results


class MemoryOptimizer:
    """Memory optimization strategies and utilities."""

    def __init__(self):
        """Initialize memory optimizer."""
        self._logger = logging.getLogger(__name__)
        self._optimization_stats = {
            "optimizations_performed": 0,
            "memory_saved_mb": 0.0,
            "last_optimization": None,
        }

    def optimize_data_structures(self, data: Any) -> Any:
        """Optimize data structures for memory efficiency.

        Args:
            data: Data to optimize

        Returns:
            Optimized data
        """
        if isinstance(data, dict):
            return self._optimize_dict(data)
        elif isinstance(data, list):
            return self._optimize_list(data)
        else:
            return data

    def _optimize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize dictionary for memory efficiency.

        Args:
            data: Dictionary to optimize

        Returns:
            Optimized dictionary
        """
        # Remove None values
        optimized = {k: v for k, v in data.items() if v is not None}

        # Recursively optimize nested structures
        for key, value in optimized.items():
            optimized[key] = self.optimize_data_structures(value)

        return optimized

    def _optimize_list(self, data: List[Any]) -> List[Any]:
        """Optimize list for memory efficiency.

        Args:
            data: List to optimize

        Returns:
            Optimized list
        """
        # Remove None values
        optimized = [item for item in data if item is not None]

        # Recursively optimize nested structures
        optimized = [self.optimize_data_structures(item) for item in optimized]

        return optimized

    def create_memory_efficient_cache(self, max_size: int = 1000) -> Dict[str, Any]:
        """Create a memory-efficient cache with LRU eviction.

        Args:
            max_size: Maximum cache size

        Returns:
            Memory-efficient cache
        """
        from collections import OrderedDict

        class LRUCache:
            def __init__(self, max_size: int):
                self.max_size = max_size
                self.cache = OrderedDict()

            def get(self, key: str) -> Optional[Any]:
                if key in self.cache:
                    # Move to end (most recently used)
                    self.cache.move_to_end(key)
                    return self.cache[key]
                return None

            def set(self, key: str, value: Any) -> None:
                if key in self.cache:
                    # Update existing key
                    self.cache.move_to_end(key)
                else:
                    # Add new key
                    if len(self.cache) >= self.max_size:
                        # Remove least recently used
                        self.cache.popitem(last=False)

                self.cache[key] = value

            def clear(self) -> None:
                self.cache.clear()

        return LRUCache(max_size)

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get memory optimization statistics.

        Returns:
            Optimization statistics dictionary
        """
        return self._optimization_stats.copy()


class MemoryManager:
    """Comprehensive memory management system."""

    def __init__(self, max_memory_mb: int = 512, enable_monitoring: bool = True):
        """Initialize memory manager.

        Args:
            max_memory_mb: Maximum memory usage in MB
            enable_monitoring: Whether to enable memory monitoring
        """
        self.monitor = MemoryMonitor(enable_monitoring)
        self.cleanup = MemoryCleanup(max_memory_mb)
        self.optimizer = MemoryOptimizer()
        self._logger = logging.getLogger(__name__)
        self._auto_cleanup_enabled = True

    async def start_auto_cleanup(self, interval_seconds: int = 60) -> None:
        """Start automatic memory cleanup.

        Args:
            interval_seconds: Cleanup interval in seconds
        """
        self._logger.info(
            f"Starting automatic memory cleanup every {interval_seconds} seconds"
        )

        while self._auto_cleanup_enabled:
            try:
                await self.check_and_cleanup()
                await asyncio.sleep(interval_seconds)
            except Exception as e:
                self._logger.error(f"Auto cleanup error: {e}")
                await asyncio.sleep(interval_seconds)

    def stop_auto_cleanup(self) -> None:
        """Stop automatic memory cleanup."""
        self._auto_cleanup_enabled = False
        self._logger.info("Stopped automatic memory cleanup")

    async def check_and_cleanup(self) -> Dict[str, Any]:
        """Check memory usage and perform cleanup if needed.

        Returns:
            Cleanup results dictionary
        """
        return await self.cleanup.check_and_cleanup()

    def get_memory_status(self) -> Dict[str, Any]:
        """Get comprehensive memory status.

        Returns:
            Memory status dictionary
        """
        status = {
            "current_usage": self.monitor.get_memory_usage(),
            "trend": self.monitor.get_memory_trend(),
            "optimization_stats": self.optimizer.get_optimization_stats(),
        }

        return status

    def register_cleanup_callback(self, callback: callable) -> None:
        """Register a cleanup callback.

        Args:
            callback: Function to call during cleanup
        """
        self.cleanup.register_cleanup_callback(callback)

    def optimize_data(self, data: Any) -> Any:
        """Optimize data for memory efficiency.

        Args:
            data: Data to optimize

        Returns:
            Optimized data
        """
        return self.optimizer.optimize_data_structures(data)


# Global memory manager instance
memory_manager = MemoryManager()


# Convenience functions
def get_memory_usage() -> Dict[str, Any]:
    """Get current memory usage.

    Returns:
        Memory usage dictionary
    """
    return memory_manager.monitor.get_memory_usage()


async def cleanup_memory() -> Dict[str, Any]:
    """Perform memory cleanup.

    Returns:
        Cleanup results dictionary
    """
    return await memory_manager.check_and_cleanup()


def optimize_data(data: Any) -> Any:
    """Optimize data for memory efficiency.

    Args:
        data: Data to optimize

    Returns:
        Optimized data
    """
    return memory_manager.optimize_data(data)


__all__ = [
    "MemoryMonitor",
    "MemoryCleanup",
    "MemoryOptimizer",
    "MemoryManager",
    "memory_manager",
    "get_memory_usage",
    "cleanup_memory",
    "optimize_data",
]
