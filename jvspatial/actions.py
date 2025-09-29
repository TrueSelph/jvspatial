"""
Actions management system for jvspatial agent framework.

This module provides a comprehensive, production-ready Actions class implementation
that manages action discovery, registration, execution, dependency resolution,
and system health monitoring for jvspatial agents.
"""

import asyncio
import importlib
import inspect
from typing import Any, Dict, List, Optional, Set, Type, Callable, Union
from collections import defaultdict
from pathlib import Path
import weakref
import logging
from dataclasses import dataclass, field
from enum import Enum

from jvspatial.core.entities import Object
from jvspatial.exceptions import (
    JVSpatialError,
    ValidationError,
    CircularReferenceError,
    EntityNotFoundError,
    WalkerExecutionError,
    ConfigurationError
)

logger = logging.getLogger(__name__)


class ActionStatus(Enum):
    """Enumeration of action status states."""
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"
    LOADING = "loading"


class ActionType(Enum):
    """Enumeration of action types."""
    ACTION = "action"
    INTERACT_ACTION = "interact_action"
    WALKER_ACTION = "walker_action"


@dataclass
class ActionInfo:
    """Information about a registered action."""
    name: str
    action_class: Type
    module_path: str
    status: ActionStatus = ActionStatus.ENABLED
    action_type: ActionType = ActionType.ACTION
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_info: Optional[str] = None
    last_updated: Optional[float] = None


class ActionRegistry:
    """Thread-safe registry for managing actions."""
    
    def __init__(self):
        self._actions: Dict[str, ActionInfo] = {}
        self._lock = asyncio.Lock()
    
    async def register(self, action_info: ActionInfo) -> None:
        """Register an action."""
        async with self._lock:
            self._actions[action_info.name] = action_info
    
    async def unregister(self, name: str) -> bool:
        """Unregister an action."""
        async with self._lock:
            return self._actions.pop(name, None) is not None
    
    async def get(self, name: str) -> Optional[ActionInfo]:
        """Get action info by name."""
        async with self._lock:
            return self._actions.get(name)
    
    async def get_all(self) -> Dict[str, ActionInfo]:
        """Get all registered actions."""
        async with self._lock:
            return self._actions.copy()
    
    async def clear(self) -> None:
        """Clear all registered actions."""
        async with self._lock:
            self._actions.clear()


class ActionEventType(Enum):
    """Types of action events."""
    REGISTERED = "registered"
    UNREGISTERED = "unregistered"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class ActionEvent:
    """Event data for action lifecycle events."""
    event_type: ActionEventType
    action_name: str
    action_info: Optional[ActionInfo] = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Actions(Object):
    """
    Comprehensive Actions management system for jvspatial agents.
    
    Provides action discovery, dynamic importing, registration/deregistration,
    state management, bulk operations, dependency management, event handling,
    and system maintenance capabilities.
    """
    
    type_code: str = "a"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._registry = ActionRegistry()
        self._event_handlers: Dict[ActionEventType, List[Callable]] = defaultdict(list)
        self._search_paths: List[Path] = []
        self._auto_discovery: bool = True
        self._dependency_cache: Dict[str, Set[str]] = {}
        self._stats = {
            "registrations": 0,
            "unregistrations": 0,
            "failures": 0,
            "last_discovery": None
        }
    
    # ============== CORE ACTION MANAGEMENT ==============
    
    async def discover_actions(self, search_paths: Optional[List[Union[str, Path]]] = None) -> Dict[str, ActionInfo]:
        """
        Discover actions in specified paths or default locations.
        
        Args:
            search_paths: Paths to search for actions
        
        Returns:
            Dictionary of discovered action info by name
        """
        if search_paths:
            self._search_paths = [Path(p) for p in search_paths]
        elif not self._search_paths:
            # Default search paths
            self._search_paths = [
                Path.cwd() / "actions",
                Path.cwd() / "jvspatial" / "actions"
            ]
        
        discovered = {}
        
        for search_path in self._search_paths:
            if not search_path.exists():
                continue
            
            try:
                actions = await self._discover_in_path(search_path)
                discovered.update(actions)
            except Exception as e:
                logger.error(f"Failed to discover actions in {search_path}: {e}")
                await self._emit_event(ActionEvent(
                    event_type=ActionEventType.ERROR,
                    action_name=f"discovery:{search_path}",
                    error=e
                ))
        
        self._stats["last_discovery"] = asyncio.get_event_loop().time()
        return discovered
    
    async def _discover_in_path(self, path: Path) -> Dict[str, ActionInfo]:
        """Discover actions in a specific path."""
        discovered = {}
        
        for py_file in path.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            
            try:
                module_path = self._path_to_module(py_file, path)
                actions = await self._extract_actions_from_module(module_path)
                discovered.update(actions)
            except Exception as e:
                logger.warning(f"Failed to process {py_file}: {e}")
        
        return discovered
    
    def _path_to_module(self, py_file: Path, base_path: Path) -> str:
        """Convert file path to module path."""
        relative_path = py_file.relative_to(base_path)
        return str(relative_path.with_suffix("")).replace("/", ".")
    
    async def _extract_actions_from_module(self, module_path: str) -> Dict[str, ActionInfo]:
        """Extract action classes from a module."""
        try:
            module = importlib.import_module(module_path)
            actions = {}
            
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if self._is_action_class(obj):
                    action_info = ActionInfo(
                        name=name,
                        action_class=obj,
                        module_path=module_path,
                        action_type=self._determine_action_type(obj),
                        dependencies=self._extract_dependencies(obj),
                        metadata=self._extract_metadata(obj)
                    )
                    actions[name] = action_info
            
            return actions
        except Exception as e:
            raise ValidationError(f"Failed to extract actions from module {module_path}: {e}")
    
    def _is_action_class(self, obj: Type) -> bool:
        """Check if a class is an action class."""
        # Basic heuristics - can be enhanced based on framework specifics
        return (
            inspect.isclass(obj) and
            hasattr(obj, "__call__") and
            not obj.__name__.startswith("_") and
            obj.__module__ != "builtins"
        )
    
    def _determine_action_type(self, action_class: Type) -> ActionType:
        """Determine the type of action."""
        class_name = action_class.__name__.lower()
        if "interact" in class_name:
            return ActionType.INTERACT_ACTION
        elif "walker" in class_name:
            return ActionType.WALKER_ACTION
        return ActionType.ACTION
    
    def _extract_dependencies(self, action_class: Type) -> Set[str]:
        """Extract dependencies from action class."""
        dependencies = set()
        
        # Check for explicit dependencies attribute
        if hasattr(action_class, "dependencies"):
            deps = action_class.dependencies
            if isinstance(deps, (list, tuple, set)):
                dependencies.update(str(dep) for dep in deps)
        
        # Check method signatures for type hints
        for method_name in ["execute", "run", "__call__"]:
            if hasattr(action_class, method_name):
                method = getattr(action_class, method_name)
                sig = inspect.signature(method)
                for param in sig.parameters.values():
                    if param.annotation != inspect.Parameter.empty:
                        if hasattr(param.annotation, "__name__"):
                            dependencies.add(param.annotation.__name__)
        
        return dependencies
    
    def _extract_metadata(self, action_class: Type) -> Dict[str, Any]:
        """Extract metadata from action class."""
        metadata = {}
        
        # Extract docstring
        if action_class.__doc__:
            metadata["description"] = action_class.__doc__.strip()
        
        # Extract version if available
        if hasattr(action_class, "__version__"):
            metadata["version"] = action_class.__version__
        
        # Extract tags if available
        if hasattr(action_class, "tags"):
            metadata["tags"] = list(action_class.tags)
        
        return metadata
    
    async def register_action(self, name: str, action_class: Type, **kwargs) -> bool:
        """
        Register a single action.
        
        Args:
            name: Action name
            action_class: Action class
            **kwargs: Additional metadata
        
        Returns:
            True if registration successful
        """
        try:
            action_info = ActionInfo(
                name=name,
                action_class=action_class,
                module_path=action_class.__module__,
                dependencies=self._extract_dependencies(action_class),
                metadata={**self._extract_metadata(action_class), **kwargs}
            )
            
            await self._registry.register(action_info)
            self._stats["registrations"] += 1
            
            await self._emit_event(ActionEvent(
                event_type=ActionEventType.REGISTERED,
                action_name=name,
                action_info=action_info
            ))
            
            # Update dependency relationships
            await self._update_dependency_relationships(action_info)
            
            return True
            
        except Exception as e:
            self._stats["failures"] += 1
            await self._emit_event(ActionEvent(
                event_type=ActionEventType.ERROR,
                action_name=name,
                error=e
            ))
            raise ValidationError(f"Failed to register action {name}: {e}")
    
    async def unregister_action(self, name: str) -> bool:
        """
        Unregister an action.
        
        Args:
            name: Action name to unregister
        
        Returns:
            True if unregistration successful
        """
        action_info = await self._registry.get(name)
        if not action_info:
            return False
        
        # Check for dependents
        if action_info.dependents:
            raise ValidationError(
                f"Cannot unregister action {name}: has dependents {action_info.dependents}",
                details={"dependents": list(action_info.dependents)}
            )
        
        success = await self._registry.unregister(name)
        if success:
            self._stats["unregistrations"] += 1
            await self._emit_event(ActionEvent(
                event_type=ActionEventType.UNREGISTERED,
                action_name=name,
                action_info=action_info
            ))
            
            # Clean up dependency relationships
            await self._cleanup_dependency_relationships(action_info)
        
        return success
    
    # ============== BULK OPERATIONS ==============
    
    async def register_multiple(self, actions: Dict[str, Type]) -> Dict[str, bool]:
        """Register multiple actions at once."""
        results = {}
        
        # Resolve registration order based on dependencies
        ordered_actions = await self._resolve_registration_order(actions)
        
        for name in ordered_actions:
            action_class = actions[name]
            try:
                results[name] = await self.register_action(name, action_class)
            except Exception as e:
                logger.error(f"Failed to register action {name}: {e}")
                results[name] = False
        
        return results
    
    async def unregister_multiple(self, names: List[str]) -> Dict[str, bool]:
        """Unregister multiple actions at once."""
        results = {}
        
        # Resolve unregistration order (reverse of dependencies)
        ordered_names = await self._resolve_unregistration_order(names)
        
        for name in ordered_names:
            try:
                results[name] = await self.unregister_action(name)
            except Exception as e:
                logger.error(f"Failed to unregister action {name}: {e}")
                results[name] = False
        
        return results
    
    async def _resolve_registration_order(self, actions: Dict[str, Type]) -> List[str]:
        """Resolve the order for registering actions based on dependencies."""
        dependency_graph = {}
        
        for name, action_class in actions.items():
            dependencies = self._extract_dependencies(action_class)
            # Only include dependencies that are in the current registration set
            filtered_deps = {dep for dep in dependencies if dep in actions}
            dependency_graph[name] = filtered_deps
        
        return self._topological_sort(dependency_graph)
    
    async def _resolve_unregistration_order(self, names: List[str]) -> List[str]:
        """Resolve the order for unregistering actions (reverse of dependencies)."""
        dependency_graph = {}
        all_actions = await self._registry.get_all()
        
        for name in names:
            if name in all_actions:
                # For unregistration, we need dependents, not dependencies
                dependents = {dep for dep in names if name in all_actions[dep].dependencies}
                dependency_graph[name] = dependents
        
        # Return reverse topological order
        return list(reversed(self._topological_sort(dependency_graph)))
    
    def _topological_sort(self, graph: Dict[str, Set[str]]) -> List[str]:
        """Perform topological sort on dependency graph."""
        in_degree = {node: 0 for node in graph}
        
        # Calculate in-degrees
        for node, deps in graph.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1
        
        # Find nodes with no incoming edges
        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            node = queue.pop(0)
            result.append(node)
            
            # Remove this node and update in-degrees
            for dep in graph.get(node, set()):
                if dep in in_degree:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        queue.append(dep)
        
        # Check for circular dependencies
        if len(result) != len(graph):
            remaining = set(graph.keys()) - set(result)
            raise CircularReferenceError(
                list(remaining),
                details={"graph": {k: list(v) for k, v in graph.items()}}
            )
        
        return result
    
    # ============== STATE MANAGEMENT ==============
    
    async def enable_action(self, name: str) -> bool:
        """Enable an action."""
        action_info = await self._registry.get(name)
        if not action_info:
            raise EntityNotFoundError("Action", name)
        
        if action_info.status != ActionStatus.ENABLED:
            action_info.status = ActionStatus.ENABLED
            action_info.error_info = None
            await self._registry.register(action_info)  # Update registry
            
            await self._emit_event(ActionEvent(
                event_type=ActionEventType.ENABLED,
                action_name=name,
                action_info=action_info
            ))
        
        return True
    
    async def disable_action(self, name: str) -> bool:
        """Disable an action."""
        action_info = await self._registry.get(name)
        if not action_info:
            raise EntityNotFoundError("Action", name)
        
        if action_info.status != ActionStatus.DISABLED:
            action_info.status = ActionStatus.DISABLED
            await self._registry.register(action_info)  # Update registry
            
            await self._emit_event(ActionEvent(
                event_type=ActionEventType.DISABLED,
                action_name=name,
                action_info=action_info
            ))
        
        return True
    
    async def get_action_status(self, name: str) -> Optional[ActionStatus]:
        """Get the status of an action."""
        action_info = await self._registry.get(name)
        return action_info.status if action_info else None
    
    # ============== SEARCH AND FILTERING ==============
    
    async def search_actions(self, 
                           query: Optional[str] = None,
                           action_type: Optional[ActionType] = None,
                           status: Optional[ActionStatus] = None,
                           tags: Optional[List[str]] = None) -> List[ActionInfo]:
        """Search actions by various criteria."""
        all_actions = await self._registry.get_all()
        results = []
        
        for action_info in all_actions.values():
            # Filter by query (name or description)
            if query:
                query_lower = query.lower()
                if not (query_lower in action_info.name.lower() or
                        query_lower in action_info.metadata.get("description", "").lower()):
                    continue
            
            # Filter by action type
            if action_type and action_info.action_type != action_type:
                continue
            
            # Filter by status
            if status and action_info.status != status:
                continue
            
            # Filter by tags
            if tags:
                action_tags = set(action_info.metadata.get("tags", []))
                if not action_tags.intersection(set(tags)):
                    continue
            
            results.append(action_info)
        
        return results
    
    async def list_actions(self, include_disabled: bool = False) -> List[str]:
        """List all action names."""
        all_actions = await self._registry.get_all()
        
        if include_disabled:
            return list(all_actions.keys())
        else:
            return [name for name, info in all_actions.items() 
                   if info.status == ActionStatus.ENABLED]
    
    async def filter_by_type(self, action_type: ActionType) -> List[ActionInfo]:
        """Filter actions by type."""
        return await self.search_actions(action_type=action_type)
    
    # ============== DEPENDENCY MANAGEMENT ==============
    
    async def _update_dependency_relationships(self, action_info: ActionInfo) -> None:
        """Update dependency relationships when registering an action."""
        all_actions = await self._registry.get_all()
        
        # Update dependencies of the new action
        for dep_name in action_info.dependencies:
            if dep_name in all_actions:
                all_actions[dep_name].dependents.add(action_info.name)
                await self._registry.register(all_actions[dep_name])
        
        # Update dependents for actions that depend on this new action
        for other_info in all_actions.values():
            if action_info.name in other_info.dependencies:
                action_info.dependents.add(other_info.name)
        
        await self._registry.register(action_info)
    
    async def _cleanup_dependency_relationships(self, action_info: ActionInfo) -> None:
        """Clean up dependency relationships when unregistering an action."""
        all_actions = await self._registry.get_all()
        
        # Remove from dependents of dependencies
        for dep_name in action_info.dependencies:
            if dep_name in all_actions:
                all_actions[dep_name].dependents.discard(action_info.name)
                await self._registry.register(all_actions[dep_name])
    
    async def get_dependencies(self, name: str) -> Set[str]:
        """Get direct dependencies of an action."""
        action_info = await self._registry.get(name)
        if not action_info:
            raise EntityNotFoundError("Action", name)
        return action_info.dependencies.copy()
    
    async def get_dependents(self, name: str) -> Set[str]:
        """Get actions that depend on this action."""
        action_info = await self._registry.get(name)
        if not action_info:
            raise EntityNotFoundError("Action", name)
        return action_info.dependents.copy()
    
    async def get_dependency_chain(self, name: str) -> List[str]:
        """Get full dependency chain for an action."""
        visited = set()
        chain = []
        
        async def _collect_deps(action_name: str):
            if action_name in visited:
                raise CircularReferenceError([action_name], 
                                           details={"current_chain": chain})
            
            visited.add(action_name)
            action_info = await self._registry.get(action_name)
            if action_info:
                for dep in action_info.dependencies:
                    await _collect_deps(dep)
                chain.append(action_name)
        
        await _collect_deps(name)
        return chain
    
    async def validate_dependencies(self) -> Dict[str, List[str]]:
        """Validate all dependency relationships and return any issues."""
        all_actions = await self._registry.get_all()
        issues = {}
        
        for name, action_info in all_actions.items():
            action_issues = []
            
            # Check for missing dependencies
            for dep in action_info.dependencies:
                if dep not in all_actions:
                    action_issues.append(f"Missing dependency: {dep}")
            
            # Check for circular dependencies
            try:
                await self.get_dependency_chain(name)
            except CircularReferenceError as e:
                action_issues.append(f"Circular dependency: {e.path}")
            
            if action_issues:
                issues[name] = action_issues
        
        return issues
    
    # ============== EVENT HANDLING ==============
    
    async def add_event_handler(self, event_type: ActionEventType, handler: Callable) -> None:
        """Add an event handler for action lifecycle events."""
        self._event_handlers[event_type].append(handler)
    
    async def remove_event_handler(self, event_type: ActionEventType, handler: Callable) -> bool:
        """Remove an event handler."""
        try:
            self._event_handlers[event_type].remove(handler)
            return True
        except ValueError:
            return False
    
    async def _emit_event(self, event: ActionEvent) -> None:
        """Emit an action event to all registered handlers."""
        handlers = self._event_handlers.get(event.event_type, [])
        
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in event handler for {event.event_type}: {e}")
    
    # ============== SYSTEM MAINTENANCE ==============
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get system statistics."""
        all_actions = await self._registry.get_all()
        
        status_counts = defaultdict(int)
        type_counts = defaultdict(int)
        
        for action_info in all_actions.values():
            status_counts[action_info.status.value] += 1
            type_counts[action_info.action_type.value] += 1
        
        return {
            "total_actions": len(all_actions),
            "status_distribution": dict(status_counts),
            "type_distribution": dict(type_counts),
            "registrations": self._stats["registrations"],
            "unregistrations": self._stats["unregistrations"],
            "failures": self._stats["failures"],
            "last_discovery": self._stats["last_discovery"]
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        health = {
            "status": "healthy",
            "issues": [],
            "warnings": []
        }
        
        try:
            # Check dependency integrity
            dependency_issues = await self.validate_dependencies()
            if dependency_issues:
                health["issues"].append({
                    "type": "dependency_issues",
                    "details": dependency_issues
                })
                health["status"] = "degraded"
            
            # Check for actions in error state
            all_actions = await self._registry.get_all()
            error_actions = [name for name, info in all_actions.items() 
                           if info.status == ActionStatus.ERROR]
            if error_actions:
                health["issues"].append({
                    "type": "error_actions",
                    "details": error_actions
                })
                health["status"] = "degraded"
            
            # Check for orphaned actions (no dependents or dependencies)
            orphaned = [name for name, info in all_actions.items()
                       if not info.dependencies and not info.dependents]
            if len(orphaned) > len(all_actions) * 0.5:  # More than 50% orphaned
                health["warnings"].append({
                    "type": "high_orphaned_ratio", 
                    "count": len(orphaned),
                    "total": len(all_actions)
                })
            
        except Exception as e:
            health["status"] = "unhealthy"
            health["issues"].append({
                "type": "health_check_error",
                "details": str(e)
            })
        
        return health
    
    async def cleanup(self) -> Dict[str, Any]:
        """Clean up system resources and perform maintenance."""
        cleanup_stats = {
            "actions_removed": 0,
            "dependencies_fixed": 0,
            "errors_cleared": 0
        }
        
        all_actions = await self._registry.get_all()
        
        # Remove actions in permanent error state
        for name, action_info in list(all_actions.items()):
            if (action_info.status == ActionStatus.ERROR and 
                action_info.error_info and 
                "permanent" in action_info.error_info.lower()):
                await self._registry.unregister(name)
                cleanup_stats["actions_removed"] += 1
        
        # Clear error states for actions that might have been fixed
        for action_info in all_actions.values():
            if action_info.status == ActionStatus.ERROR:
                try:
                    # Try to re-validate the action
                    if hasattr(action_info.action_class, "__call__"):
                        action_info.status = ActionStatus.ENABLED
                        action_info.error_info = None
                        await self._registry.register(action_info)
                        cleanup_stats["errors_cleared"] += 1
                except Exception:
                    pass  # Keep in error state
        
        return cleanup_stats
    
    async def reset(self) -> None:
        """Reset the entire action system."""
        await self._registry.clear()
        self._event_handlers.clear()
        self._dependency_cache.clear()
        self._stats = {
            "registrations": 0,
            "unregistrations": 0,
            "failures": 0,
            "last_discovery": None
        }
    
    # ============== INITIALIZATION AND BOOTSTRAP ==============
    
    async def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the action system with optional configuration."""
        if config:
            self._auto_discovery = config.get("auto_discovery", True)
            if "search_paths" in config:
                self._search_paths = [Path(p) for p in config["search_paths"]]
        
        if self._auto_discovery:
            await self.discover_actions()
            discovered = await self.discover_actions()
            await self.register_multiple({info.name: info.action_class 
                                        for info in discovered.values()})
    
    async def bootstrap(self, essential_actions: Optional[List[str]] = None) -> bool:
        """Bootstrap the system with essential actions."""
        try:
            if essential_actions:
                all_actions = await self._registry.get_all()
                missing = [name for name in essential_actions if name not in all_actions]
                if missing:
                    raise ConfigurationError(
                        f"Essential actions missing: {missing}",
                        details={"missing_actions": missing}
                    )
                
                # Enable all essential actions
                for name in essential_actions:
                    await self.enable_action(name)
            
            return True
        except Exception as e:
            logger.error(f"Bootstrap failed: {e}")
            return False