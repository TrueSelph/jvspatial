"""Decorator functions for jvspatial entities."""

import inspect
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Optional, Type, Union

if TYPE_CHECKING:
    from .entities import Edge, Node, Walker


def _set_hook_attributes(
    func: Callable[..., Any], targets: Optional[Any] = None
) -> None:
    """Set hook attributes on a function.

    This helper exists to centralize the function attribute modification and
    avoid individual setattr calls that trigger B010.
    """
    func._visit_targets = targets  # type: ignore[attr-defined]
    func._is_visit_hook = True  # type: ignore[attr-defined]


def on_visit(*target_types: Union[Type[Union["Node", "Edge", "Walker"]], str]):
    """Register a visit hook for one or more target types.

    Args:
        *target_types: One or more target types (Node, Edge, Walker subclasses, or string names)
                      If empty, defaults to any valid type based on context
                      Strings will be resolved to actual classes at runtime

    Examples:
        @on_visit(NodeA, NodeB)           # Triggers for NodeA OR NodeB
        @on_visit(WalkerA, WalkerB)       # Triggers for WalkerA OR WalkerB
        @on_visit()                       # Triggers for any valid type
        @on_visit                         # Triggers for any valid type (no parentheses)
        @on_visit(Highway, Railroad)      # Triggers for Highway OR Railroad edges
        @on_visit("WebhookEvent")         # Triggers for WebhookEvent (string resolved at runtime)
    """
    # Handle case where @on_visit is used without parentheses
    if (
        len(target_types) == 1
        and callable(target_types[0])
        and not inspect.isclass(target_types[0])
        and not isinstance(target_types[0], str)
    ):
        # This is the case: @on_visit (without parentheses)
        func = target_types[0]
        _set_hook_attributes(func)
        return func

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # Validate target types - allow strings for forward references
        for target_type in target_types:
            if not (inspect.isclass(target_type) or isinstance(target_type, str)):
                raise ValueError(
                    f"Target type must be a class or string, got {target_type}"
                )
        _set_hook_attributes(func, target_types if target_types else None)
        return func

    return decorator


def on_exit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate methods to execute when walker completes traversal.

    Args:
        func: The function to decorate
    """
    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        async_wrapper._on_exit = True  # type: ignore[attr-defined]
        return async_wrapper
    else:

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        sync_wrapper._on_exit = True  # type: ignore[attr-defined]
        return sync_wrapper
