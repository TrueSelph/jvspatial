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

    # In your code (deferred mode is on at construct when globally allowed):
    entity = await MyEntity.get(entity_id)
    # Optional: entity.enable_deferred_saves()  # idempotent; use after flush()
    # to start a new batch in the same session.

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

Serverless:
    In serverless mode (`is_serverless_mode()`), deferred saves are always
    disabled regardless of this env var. Use `deferred_saves_globally_allowed()`
    for the effective runtime check.

Multi-entity:
    Use `flush_deferred_entities(interaction, conversation, strict=False)` to
    call `flush()` on several objects; pass `strict=True` to fail the request
    on the first flush error.
"""

import inspect
import logging
from typing import Any, ClassVar, Optional, Protocol

from jvspatial.env import load_env
from jvspatial.runtime.serverless import is_serverless_mode

logger = logging.getLogger(__name__)


class _SaveableProtocol(Protocol):
    """Protocol defining the save method expected from the base class."""

    async def save(self, *args: Any, **kwargs: Any) -> Any:
        """Save the entity to the database."""
        ...


def _env_allows_deferred_saves() -> bool:
    """Whether JVSPATIAL_ENABLE_DEFERRED_SAVES permits deferred saves (via load_env cache)."""
    return load_env().enable_deferred_saves


def deferred_saves_globally_allowed(config: Optional[Any] = None) -> bool:
    """Return True if deferred batching is allowed (env on and not serverless).

    Reflects both ``JVSPATIAL_ENABLE_DEFERRED_SAVES`` (via :func:`load_env`) and
    :func:`is_serverless_mode`. ``EnvConfig.enable_deferred_saves`` is the raw env
    flag only; use this function for effective batching policy at runtime.
    """
    return _env_allows_deferred_saves() and not is_serverless_mode(config)


async def flush_deferred_entities(*entities: Any, strict: bool = False) -> bool:
    """Flush entities that expose ``flush`` (e.g. :class:`DeferredSaveMixin`).

    Skips ``None`` and objects without a callable ``flush``. For each entity,
    ``await entity.flush()`` ends deferred batching and persists when dirty.

    Args:
        *entities: Interaction, conversation, or any saveable with ``flush``.
        strict: If False, log errors and continue; return False if any failed.
            If True, log and re-raise the first exception.

    Returns:
        True if every flush succeeded or was skipped; False if any failed
        (only when strict is False).
    """
    success = True
    for entity in entities:
        if entity is None:
            continue
        flush_fn = getattr(entity, "flush", None)
        if flush_fn is None or not callable(flush_fn):
            continue
        try:
            result = flush_fn()
            if inspect.isawaitable(result):
                await result
        except Exception as e:
            eid = getattr(entity, "id", "unknown")
            logger.error(
                "Failed to flush %s %s: %s",
                entity.__class__.__name__,
                eid,
                e,
            )
            success = False
            if strict:
                raise
    return success


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

    ClassVar:
        deferred_saves_auto_on_init: When True (default), new instances start
        with deferred batching enabled if :func:`deferred_saves_globally_allowed`
        is true. Set to False on a subclass to keep deferred mode off until
        :meth:`enable_deferred_saves` is called.
    """

    deferred_saves_auto_on_init: ClassVar[bool] = True

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
        self._dirty = False
        if self.deferred_saves_auto_on_init and deferred_saves_globally_allowed():
            self._deferred_save_mode = True
        else:
            self._deferred_save_mode = False

    def enable_deferred_saves(self) -> None:
        """Enable deferred save mode for this instance (optional at construct time).

        New instances already enable deferred batching when
        :func:`deferred_saves_globally_allowed` is true unless
        ``deferred_saves_auto_on_init`` is false on the class. Call this to
        re-enable after :meth:`flush` or to turn batching on explicitly.
        """
        if not deferred_saves_globally_allowed():
            logger.debug(
                "enable_deferred_saves ignored: deferred saves disabled "
                "(serverless mode or JVSPATIAL_ENABLE_DEFERRED_SAVES=false)"
            )
            return
        self._deferred_save_mode = True

    def disable_deferred_saves(self) -> None:
        """Disable deferred save mode without persisting.

        Prefer :meth:`flush` to end a batching session (it persists when dirty and
        always clears deferred mode). Use this only when you must turn off
        batching without writing.
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

        If deferred save mode is enabled (from construction, via
        :meth:`enable_deferred_saves`, or after a failed :meth:`flush` retry
        path) and deferred_saves_globally_allowed() is True, this method marks
        the entity as dirty without performing the database write.

        Otherwise, it performs the save immediately by calling the
        parent class's save() method.

        Args:
            *args: Positional arguments passed to parent save().
            **kwargs: Keyword arguments passed to parent save().

        Returns:
            The result of the parent save() method, or None if deferred.
        """
        if deferred_saves_globally_allowed() and self._deferred_save_mode:
            self._dirty = True
            return None
        return await self._super_save(*args, **kwargs)

    async def flush(self) -> None:
        """End deferred batching for this instance and persist if dirty.

        Always clears deferred save mode when this call completes successfully,
        including when there is nothing dirty (so later ``save()`` calls are not
        stuck in batching mode).

        When dirty, temporarily disables deferred mode, performs the underlying
        ``save()`` with no arguments, then clears the dirty flag on success.

        Note:
            Callers must not rely on arguments passed to ``save()`` being
            applied at flush time.

        Raises:
            Exception: Re-raises any exception from save(), preserving
                dirty state and deferred mode for retry.
        """
        if not self._dirty:
            self._deferred_save_mode = False
            return

        self._deferred_save_mode = False
        try:
            await self._super_save()
            self._dirty = False
        except Exception as e:
            self._deferred_save_mode = True
            logger.error(
                f"Failed to flush deferred save for {self.__class__.__name__}: {e}"
            )
            raise
