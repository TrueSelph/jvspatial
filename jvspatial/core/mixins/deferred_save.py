"""Deferred save mixin for batching database writes.

This mixin provides a deferred save pattern that allows multiple in-memory
updates to an entity to be batched into a single database write. This is
particularly useful for entities that experience rapid, sequential updates
during a single operation (e.g., conversation metadata updates during
an interaction).

Usage:
    from jvspatial.core import Node
    from jvspatial.core.mixins import DeferredSaveMixin

    class MyEntity(DeferredSaveMixin, Node):
        # ... entity definition ...
        pass

    # In your code:
    entity = await MyEntity.get(entity_id)
    entity.enable_deferred_saves()

    # Multiple updates - no database writes yet
    entity.field1 = "value1"
    await entity.save()  # Marks dirty, doesn't write
    entity.field2 = "value2"
    await entity.save()  # Still just marks dirty

    # Single database write at the end
    await entity.flush()

Environment Variable:
    JVSPATIAL_ENABLE_DEFERRED_SAVES: Set to "true" (default) to enable
    the deferred save optimization. Set to "false" to disable and have
    all save() calls write immediately.
"""

import logging
import os
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class _SaveableProtocol(Protocol):
    """Protocol defining the save method expected from the base class."""

    async def save(self, *args: Any, **kwargs: Any) -> Any:
        """Save the entity to the database."""
        ...


# Global configuration for deferred saves
# Default to "true" to enable the optimization
ENABLE_DEFERRED_SAVES = (
    os.getenv("JVSPATIAL_ENABLE_DEFERRED_SAVES", "true").lower() == "true"
)


class DeferredSaveMixin:
    """Mixin that adds deferred save capability to jvspatial entities.

    This mixin intercepts save() calls and can defer them until flush()
    is called, allowing multiple updates to be batched into a single
    database write.

    Attributes:
        _deferred_save_mode: Whether deferred saves are currently enabled
            for this instance.
        _dirty: Whether this instance has pending changes that need to
            be flushed to the database.

    Note:
        The mixin should be placed BEFORE the base class in the inheritance
        list to ensure proper method resolution order (MRO):

            class MyEntity(DeferredSaveMixin, Node):  # Correct
            class MyEntity(Node, DeferredSaveMixin):  # Incorrect
    """

    _deferred_save_mode: bool
    _dirty: bool

    async def _super_save(self, *args: Any, **kwargs: Any) -> Any:
        """Call the parent class save method.

        This method exists to satisfy type checkers. The actual save()
        implementation comes from the base class (e.g., Node) via MRO.
        """
        # Cast to protocol to satisfy mypy - actual implementation comes from MRO
        parent_save = super().save  # type: ignore[misc]
        return await parent_save(*args, **kwargs)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the mixin with deferred save state.

        Args:
            *args: Positional arguments passed to parent class.
            **kwargs: Keyword arguments passed to parent class.
        """
        super().__init__(*args, **kwargs)
        self._deferred_save_mode = False
        self._dirty = False

    def enable_deferred_saves(self) -> None:
        """Enable deferred save mode for this instance.

        When enabled, calls to save() will mark the entity as dirty
        but will not perform the actual database write. Use flush()
        to force a save when ready.

        This is useful when you know an entity will be updated multiple
        times in sequence and you want to batch those updates into a
        single database write for performance.
        """
        self._deferred_save_mode = True

    def disable_deferred_saves(self) -> None:
        """Disable deferred save mode for this instance.

        After disabling, calls to save() will perform immediate
        database writes as normal.

        Note: This does NOT automatically flush pending changes.
        Call flush() first if you have dirty data that needs to
        be persisted.
        """
        self._deferred_save_mode = False

    @property
    def is_dirty(self) -> bool:
        """Check if this instance has pending changes.

        Returns:
            True if there are unflushed changes, False otherwise.
        """
        return self._dirty

    @property
    def deferred_saves_enabled(self) -> bool:
        """Check if deferred save mode is currently enabled.

        Returns:
            True if deferred saves are enabled, False otherwise.
        """
        return self._deferred_save_mode

    async def save(self, *args: Any, **kwargs: Any) -> Any:
        """Save the entity with deferred mode support.

        If deferred save mode is enabled (via enable_deferred_saves())
        and the global ENABLE_DEFERRED_SAVES is True, this method marks
        the entity as dirty without performing the database write.

        Otherwise, it performs the save immediately by calling the
        parent class's save() method.

        Args:
            *args: Positional arguments passed to parent save().
            **kwargs: Keyword arguments passed to parent save().

        Returns:
            The result of the parent save() method, or None if deferred.
        """
        if ENABLE_DEFERRED_SAVES and self._deferred_save_mode:
            self._dirty = True
            return None
        return await self._super_save(*args, **kwargs)

    async def flush(self) -> None:
        """Force save if there are pending changes.

        If the entity has been marked as dirty (has pending changes
        from deferred save() calls), this method:
        1. Disables deferred save mode temporarily
        2. Performs the actual database write
        3. Clears the dirty flag only on success

        If the entity is not dirty, this method does nothing.

        This should be called when you're done making updates and
        want to persist all accumulated changes to the database.

        Raises:
            Exception: Re-raises any exception from save(), preserving
                the dirty state so flush() can be retried.
        """
        if self._dirty:
            # Temporarily disable deferred mode to allow save() to proceed
            self._deferred_save_mode = False
            try:
                await self._super_save()
                # Only clear dirty flag if save succeeds
                self._dirty = False
            except Exception as e:
                # Re-enable deferred mode so entity remains in correct state for retry
                self._deferred_save_mode = True
                logger.error(
                    f"Failed to flush deferred save for {self.__class__.__name__}: {e}"
                )
                raise
