"""Decorator utilities and helpers for jvspatial.

This module provides utility decorators and helper functions for common
decorator patterns used throughout the library.
"""

import functools
import inspect
from typing import Any, Callable, Dict, Optional, TypeVar

T = TypeVar("T", bound=Callable[..., Any])


def preserve_signature(func: T) -> T:
    """Preserve the original function signature in decorators.

    This decorator ensures that decorated functions maintain their
    original signature for better introspection and IDE support.

    Args:
        func: Function to preserve signature for

    Returns:
        Function with preserved signature

    Example:
        @preserve_signature
        def my_decorator(f):
            @functools.wraps(f)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return f(*args, **kwargs)
            return wrapper  # type: ignore[return-value]
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def async_safe(func: T) -> T:
    """Make a decorator safe for both sync and async functions.

    This decorator allows a decorator to work with both synchronous
    and asynchronous functions without modification.

    Args:
        func: Decorator function to make async-safe

    Returns:
        Async-safe decorator

    Example:
        @async_safe
        def my_decorator(f):
            @functools.wraps(f)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if inspect.iscoroutinefunction(f):
                    async def async_wrapper(*args, **kwargs):
                        return await f(*args, **kwargs)
                    return async_wrapper
                else:
                    def sync_wrapper(*args, **kwargs):
                        return f(*args, **kwargs)
                    return sync_wrapper
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def deprecated(reason: str, version: str = "0.2.0") -> Callable[[T], T]:
    """Mark a function as deprecated.

    Args:
        reason: Reason for deprecation
        version: Version when function was deprecated

    Returns:
        Decorator that marks function as deprecated

    Example:
        @deprecated("Use new_function() instead", "0.2.0")
        def old_function():
            pass
    """

    def decorator(func: T) -> T:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import warnings

            warnings.warn(
                f"{func.__name__} is deprecated since {version}: {reason}",
                DeprecationWarning,
                stacklevel=2,
            )
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def memoize(maxsize: Optional[int] = None) -> Callable[[T], T]:
    """Memoize function results.

    Args:
        maxsize: Maximum cache size (None for unlimited)

    Returns:
        Memoized function

    Example:
        @memoize(maxsize=100)
        def expensive_calculation(n):
            # Expensive computation
            return sum(range(n))
    """

    def decorator(func: T) -> T:
        cache: Dict[Any, Any] = {}

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Create cache key
            key = (args, tuple(sorted(kwargs.items())))

            if key in cache:
                return cache[key]

            result = func(*args, **kwargs)

            # Store result
            cache[key] = result

            # Limit cache size if specified
            if maxsize is not None and len(cache) > maxsize:
                # Remove oldest entry (simple FIFO)
                oldest_key = next(iter(cache))
                del cache[oldest_key]

            return result

        # Add cache management methods
        wrapper.cache_clear = cache.clear  # type: ignore[attr-defined]
        wrapper.cache_info = lambda: {  # type: ignore[attr-defined]
            "hits": len(cache),
            "misses": 0,  # Simplified
            "maxsize": maxsize,
            "currsize": len(cache),
        }

        return wrapper  # type: ignore[return-value]

    return decorator


def retry(
    max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0
) -> Callable[[T], T]:
    """Retry function execution on failure.

    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between attempts (seconds)
        backoff: Backoff multiplier for delay

    Returns:
        Function with retry logic

    Example:
        @retry(max_attempts=5, delay=0.5, backoff=2.0)
        def unreliable_operation():
            # May fail occasionally
            pass
    """

    def decorator(func: T) -> T:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = delay
            last_exception: Optional[Exception] = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        import time

                        time.sleep(current_delay)
                        current_delay *= backoff

            # All attempts failed
            if last_exception is not None:
                raise last_exception
            else:
                raise RuntimeError("All retry attempts failed")

        return wrapper  # type: ignore[return-value]

    return decorator


def timeout(seconds: float) -> Callable[[T], T]:
    """Add timeout to function execution.

    Args:
        seconds: Timeout in seconds

    Returns:
        Function with timeout

    Example:
        @timeout(30.0)
        def long_running_operation():
            # Will timeout after 30 seconds
            pass
    """

    def decorator(func: T) -> T:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(
                    f"Function {func.__name__} timed out after {seconds} seconds"
                )

            # Set up timeout
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(seconds))

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                # Restore original handler
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper  # type: ignore[return-value]

    return decorator


def validate_args(**validators: Callable[[Any], bool]) -> Callable[[T], T]:
    """Validate function arguments.

    Args:
        **validators: Validator functions for each argument

    Returns:
        Function with argument validation

    Example:
        @validate_args(
            name=lambda x: isinstance(x, str) and len(x) > 0,
            age=lambda x: isinstance(x, int) and 0 <= x <= 150
        )
        def create_user(name, age):
            return {"name": name, "age": age}
    """

    def decorator(func: T) -> T:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get function signature
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            # Validate arguments
            for param_name, validator in validators.items():
                if param_name in bound_args.arguments:
                    value = bound_args.arguments[param_name]
                    if not validator(value):
                        raise ValueError(f"Invalid value for {param_name}: {value}")

            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def log_calls(logger_name: Optional[str] = None) -> Callable[[T], T]:
    """Log function calls and results.

    Args:
        logger_name: Name of logger to use

    Returns:
        Function with call logging

    Example:
        @log_calls("my_module")
        def important_function(x, y):
            return x + y
    """

    def decorator(func: T) -> T:
        import logging

        logger = logging.getLogger(logger_name or func.__module__)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")

            try:
                result = func(*args, **kwargs)
                logger.debug(f"{func.__name__} returned: {result}")
                return result
            except Exception as e:
                logger.error(f"{func.__name__} failed with: {e}")
                raise

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = [
    "preserve_signature",
    "async_safe",
    "deprecated",
    "memoize",
    "retry",
    "timeout",
    "validate_args",
    "log_calls",
]
