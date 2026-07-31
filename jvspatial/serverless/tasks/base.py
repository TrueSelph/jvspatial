"""Base task scheduler interfaces for serverless integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RetryConfig:
    """Generic retry policy for scheduled tasks.

    Reserved for queue-based backends; Lambda async invoke currently ignores this.
    """

    max_attempts: int = 3
    backoff_seconds: int = 5


class TaskScheduler(ABC):
    """Provider-agnostic scheduler interface."""

    @abstractmethod
    def schedule(
        self,
        task_type: str,
        payload: Any,
        delay_seconds: int = 0,
        retry_config: Optional[RetryConfig] = None,
        run_at: Optional[float] = None,
        strict: bool = False,
    ) -> str:
        """Schedule a task and return provider reference id.

        Args:
            task_type: Stable namespaced task id (e.g. ``app.whatsapp.media_batch``).
            payload: JSON-serializable task input.
            delay_seconds: Minimum delay before execution (relative), when ``run_at`` unset.
            retry_config: Optional retry metadata for queue-based backends.
            run_at: Optional Unix epoch seconds for absolute execution time; backends
                map this to native scheduling (e.g. EventBridge) or embed in the message.
            strict: When True, a dispatch that cannot be handed to the provider MUST
                raise instead of logging and returning a synthetic reference. A
                caller passing ``strict=True`` is stating that it has fallback
                behaviour of its own (retry, 5xx to the webhook origin, releasing a
                dedup claim) and that a silently-dropped task is data loss. The
                default preserves fire-and-forget semantics.
        """
