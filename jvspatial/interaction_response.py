"""
InteractionResponse module for jvspatial agent framework.

This module implements the complete interaction response system based on the original
Jaseci interaction_response.jac, providing message management with typed messages,
token tracking, asynchronous persistence, and proper error handling.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from typing import ClassVar
except ImportError:
    from typing_extensions import ClassVar

from jvspatial.core.entities import Object
from jvspatial.exceptions import ValidationError


class MessageType(Enum):
    """Enumeration of supported message types."""

    SILENT = "silent"
    TEXT = "text"
    MEDIA = "media"
    MULTI = "multi"


class MediaType(Enum):
    """Enumeration of supported media types."""

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    FILE = "file"


@dataclass
class TokenUsage:
    """Token usage tracking for interactions."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_estimate: Optional[float] = None
    model_used: Optional[str] = None

    def __post_init__(self):
        """Ensure total_tokens is calculated correctly."""
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens

    def add_usage(self, other: "TokenUsage") -> "TokenUsage":
        """Add another token usage to this one."""
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_estimate=(self.cost_estimate or 0) + (other.cost_estimate or 0),
            model_used=self.model_used or other.model_used,
        )


class InteractionMessage(ABC):
    """
    Abstract base class for all interaction messages.

    Provides the interface that all message types must implement,
    with proper async/await patterns and error handling.
    """

    def __init__(
        self, message_id: Optional[str] = None, timestamp: Optional[datetime] = None
    ):
        self.message_id = message_id or str(uuid.uuid4())
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.metadata: Dict[str, Any] = {}

    @property
    @abstractmethod
    def message_type(self) -> MessageType:
        """Get the message type."""
        pass

    @abstractmethod
    async def serialize(self) -> Dict[str, Any]:
        """Serialize the message to a dictionary."""
        pass

    @classmethod
    @abstractmethod
    async def deserialize(cls, data: Dict[str, Any]) -> "InteractionMessage":
        """Deserialize a dictionary to a message instance."""
        pass

    @abstractmethod
    async def validate(self) -> bool:
        """Validate the message content."""
        pass

    async def get_size(self) -> int:
        """Get approximate size of the message in bytes."""
        serialized = await self.serialize()
        return len(str(serialized).encode("utf-8"))

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the message."""
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata from the message."""
        return self.metadata.get(key, default)


class SilentInteractionMessage(InteractionMessage):
    """
    Silent message type that carries no visible content.

    Used for system messages, acknowledgments, or hidden state transfers.
    """

    def __init__(self, system_data: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(**kwargs)
        self.system_data = system_data or {}

    @property
    def message_type(self) -> MessageType:
        """Return the message type for silent messages."""
        return MessageType.SILENT

    async def serialize(self) -> Dict[str, Any]:
        """Serialize silent message."""
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "timestamp": self.timestamp.isoformat(),
            "system_data": self.system_data,
            "metadata": self.metadata,
        }

    @classmethod
    async def deserialize(cls, data: Dict[str, Any]) -> "SilentInteractionMessage":
        """Deserialize silent message."""
        try:
            return cls(
                message_id=data.get("message_id"),
                timestamp=(
                    datetime.fromisoformat(data["timestamp"])
                    if "timestamp" in data
                    else None
                ),
                system_data=data.get("system_data", {}),
            )
        except Exception as e:
            raise ValidationError(
                f"Failed to deserialize SilentInteractionMessage: {e}"
            )

    async def validate(self) -> bool:
        """Validate silent message."""
        return isinstance(self.system_data, dict)


class TextInteractionMessage(InteractionMessage):
    """
    Text-based interaction message.

    Supports rich text content with optional formatting and styling.
    """

    def __init__(
        self, text: str, formatting: Optional[Dict[str, Any]] = None, **kwargs
    ):
        super().__init__(**kwargs)
        if not text:
            raise ValidationError("Text content cannot be empty")
        self.text = text
        self.formatting = formatting or {}

    @property
    def message_type(self) -> MessageType:
        """Return the message type for text messages."""
        return MessageType.TEXT

    async def serialize(self) -> Dict[str, Any]:
        """Serialize text message."""
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "timestamp": self.timestamp.isoformat(),
            "text": self.text,
            "formatting": self.formatting,
            "metadata": self.metadata,
        }

    @classmethod
    async def deserialize(cls, data: Dict[str, Any]) -> "TextInteractionMessage":
        """Deserialize text message."""
        try:
            return cls(
                message_id=data.get("message_id"),
                timestamp=(
                    datetime.fromisoformat(data["timestamp"])
                    if "timestamp" in data
                    else None
                ),
                text=data["text"],
                formatting=data.get("formatting", {}),
            )
        except Exception as e:
            raise ValidationError(f"Failed to deserialize TextInteractionMessage: {e}")

    async def validate(self) -> bool:
        """Validate text message."""
        return bool(self.text and isinstance(self.text, str))

    def get_plain_text(self) -> str:
        """Get plain text without formatting."""
        return self.text

    def get_word_count(self) -> int:
        """Get approximate word count."""
        return len(self.text.split())

    def get_character_count(self) -> int:
        """Get character count."""
        return len(self.text)


@dataclass
class MediaContent:
    """Container for media content with metadata."""

    content: Union[bytes, str, Path]  # Binary data, URL, or file path
    media_type: MediaType
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None  # For audio/video
    dimensions: Optional[Dict[str, int]] = (
        None  # For images/video: {"width": X, "height": Y}
    )

    async def validate(self) -> bool:
        """Validate media content."""
        if not self.content:
            return False

        # If content is a Path, check if file exists
        if isinstance(self.content, Path):
            return self.content.exists()

        return True

    async def get_size(self) -> int:
        """Get size of media content."""
        if self.size_bytes:
            return self.size_bytes

        if isinstance(self.content, bytes):
            return len(self.content)
        elif isinstance(self.content, Path) and self.content.exists():
            return self.content.stat().st_size
        elif isinstance(self.content, str):
            return len(self.content.encode("utf-8"))

        return 0


class MediaInteractionMessage(InteractionMessage):
    """
    Media-based interaction message.

    Supports various media types including images, audio, video, and documents.
    """

    def __init__(
        self, media_content: MediaContent, caption: Optional[str] = None, **kwargs
    ):
        super().__init__(**kwargs)
        self.media_content = media_content
        self.caption = caption

    @property
    def message_type(self) -> MessageType:
        """Return the message type for media messages."""
        return MessageType.MEDIA

    async def serialize(self) -> Dict[str, Any]:
        """Serialize media message."""
        # Handle content serialization based on type
        content_data = None
        if isinstance(self.media_content.content, bytes):
            # For binary data, we might want to store as base64 or reference
            content_data = {
                "type": "binary",
                "size": len(self.media_content.content),
                # Note: In production, binary data should be stored separately
            }
        elif isinstance(self.media_content.content, Path):
            content_data = {"type": "path", "path": str(self.media_content.content)}
        elif isinstance(self.media_content.content, str):
            content_data = {"type": "url", "url": self.media_content.content}

        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "timestamp": self.timestamp.isoformat(),
            "content_data": content_data,
            "media_type": self.media_content.media_type.value,
            "filename": self.media_content.filename,
            "mime_type": self.media_content.mime_type,
            "size_bytes": self.media_content.size_bytes,
            "duration_seconds": self.media_content.duration_seconds,
            "dimensions": self.media_content.dimensions,
            "caption": self.caption,
            "metadata": self.metadata,
        }

    @classmethod
    async def deserialize(cls, data: Dict[str, Any]) -> "MediaInteractionMessage":
        """Deserialize media message."""
        try:
            content_data = data["content_data"]

            # Reconstruct content based on type
            if content_data["type"] == "path":
                content = Path(content_data["path"])
            elif content_data["type"] == "url":
                content = content_data["url"]
            else:
                # For binary data, we'd need to retrieve from storage
                raise ValidationError("Binary content deserialization not implemented")

            media_content = MediaContent(
                content=content,
                media_type=MediaType(data["media_type"]),
                filename=data.get("filename"),
                mime_type=data.get("mime_type"),
                size_bytes=data.get("size_bytes"),
                duration_seconds=data.get("duration_seconds"),
                dimensions=data.get("dimensions"),
            )

            return cls(
                message_id=data.get("message_id"),
                timestamp=(
                    datetime.fromisoformat(data["timestamp"])
                    if "timestamp" in data
                    else None
                ),
                media_content=media_content,
                caption=data.get("caption"),
            )
        except Exception as e:
            raise ValidationError(f"Failed to deserialize MediaInteractionMessage: {e}")

    async def validate(self) -> bool:
        """Validate media message."""
        return await self.media_content.validate()

    async def get_size(self) -> int:
        """Get size including media content."""
        base_size = await super().get_size()
        media_size = await self.media_content.get_size()
        return base_size + media_size


class MultiInteractionMessage(InteractionMessage):
    """
    Multi-part interaction message.

    Contains multiple sub-messages of different types, useful for complex
    interactions that need to convey multiple pieces of information.
    """

    def __init__(self, messages: List[InteractionMessage], **kwargs):
        super().__init__(**kwargs)
        if not messages:
            raise ValidationError(
                "MultiInteractionMessage must contain at least one message"
            )
        self.messages = messages

    @property
    def message_type(self) -> MessageType:
        """Return the message type for multi messages."""
        return MessageType.MULTI

    async def serialize(self) -> Dict[str, Any]:
        """Serialize multi message."""
        serialized_messages = []
        for msg in self.messages:
            serialized_messages.append(await msg.serialize())

        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "timestamp": self.timestamp.isoformat(),
            "messages": serialized_messages,
            "metadata": self.metadata,
        }

    @classmethod
    async def deserialize(cls, data: Dict[str, Any]) -> "MultiInteractionMessage":
        """Deserialize multi message."""
        try:
            messages: List[InteractionMessage] = []
            for msg_data in data["messages"]:
                msg_type = MessageType(msg_data["message_type"])
                msg: InteractionMessage

                if msg_type == MessageType.SILENT:
                    msg = await SilentInteractionMessage.deserialize(msg_data)
                elif msg_type == MessageType.TEXT:
                    msg = await TextInteractionMessage.deserialize(msg_data)
                elif msg_type == MessageType.MEDIA:
                    msg = await MediaInteractionMessage.deserialize(msg_data)
                elif msg_type == MessageType.MULTI:
                    msg = await MultiInteractionMessage.deserialize(msg_data)
                else:
                    raise ValidationError(f"Unknown message type: {msg_type}")

                messages.append(msg)

            return cls(
                message_id=data.get("message_id"),
                timestamp=(
                    datetime.fromisoformat(data["timestamp"])
                    if "timestamp" in data
                    else None
                ),
                messages=messages,
            )
        except Exception as e:
            raise ValidationError(f"Failed to deserialize MultiInteractionMessage: {e}")

    async def validate(self) -> bool:
        """Validate multi message."""
        if not self.messages:
            return False

        # Collect all validation results first
        validation_results = [await msg.validate() for msg in self.messages]
        return all(validation_results)

    async def get_size(self) -> int:
        """Get total size of all messages."""
        base_size = await super().get_size()

        total_size = base_size
        for msg in self.messages:
            total_size += await msg.get_size()

        return total_size

    def get_messages_by_type(
        self, message_type: MessageType
    ) -> List[InteractionMessage]:
        """Get all messages of a specific type."""
        return [msg for msg in self.messages if msg.message_type == message_type]

    def get_text_content(self) -> str:
        """Get concatenated text content from all text messages."""
        text_messages = self.get_messages_by_type(MessageType.TEXT)
        return " ".join(msg.text for msg in text_messages if hasattr(msg, "text"))


class InteractionResponse(Object):
    """
    Comprehensive interaction response management system.

    Manages collections of interaction messages with token tracking,
    async persistence, and proper error handling following jvspatial patterns.
    """

    type_code: ClassVar[str] = "ir"

    def __init__(
        self,
        interaction_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.interaction_id = interaction_id or str(uuid.uuid4())
        self.session_id = session_id
        self.messages: List[InteractionMessage] = []
        self.token_usage = TokenUsage()
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.status = "active"
        self.error_info: Optional[str] = None

    # ============== MESSAGE MANAGEMENT ==============

    async def add_message(self, message: InteractionMessage) -> None:
        """Add a message to the response."""
        if not await message.validate():
            raise ValidationError(f"Invalid message: {message.message_id}")

        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc)
        await self.save()

    async def add_text(
        self, text: str, formatting: Optional[Dict[str, Any]] = None
    ) -> TextInteractionMessage:
        """Add a text message to the response."""
        message = TextInteractionMessage(text=text, formatting=formatting)
        await self.add_message(message)
        return message

    async def add_media(
        self, media_content: MediaContent, caption: Optional[str] = None
    ) -> MediaInteractionMessage:
        """Add a media message to the response."""
        message = MediaInteractionMessage(media_content=media_content, caption=caption)
        await self.add_message(message)
        return message

    async def add_silent(
        self, system_data: Optional[Dict[str, Any]] = None
    ) -> SilentInteractionMessage:
        """Add a silent message to the response."""
        message = SilentInteractionMessage(system_data=system_data)
        await self.add_message(message)
        return message

    async def add_multi(
        self, messages: List[InteractionMessage]
    ) -> MultiInteractionMessage:
        """Add a multi-part message to the response."""
        message = MultiInteractionMessage(messages=messages)
        await self.add_message(message)
        return message

    async def remove_message(self, message_id: str) -> bool:
        """Remove a message by ID."""
        for i, msg in enumerate(self.messages):
            if msg.message_id == message_id:
                del self.messages[i]
                self.updated_at = datetime.now(timezone.utc)
                await self.save()
                return True
        return False

    async def get_message(self, message_id: str) -> Optional[InteractionMessage]:
        """Get a message by ID."""
        for msg in self.messages:
            if msg.message_id == message_id:
                return msg
        return None

    async def clear_messages(self) -> None:
        """Clear all messages."""
        self.messages.clear()
        self.updated_at = datetime.now(timezone.utc)
        await self.save()

    # ============== FILTERING AND SEARCH ==============

    def get_messages_by_type(
        self, message_type: MessageType
    ) -> List[InteractionMessage]:
        """Get all messages of a specific type."""
        return [msg for msg in self.messages if msg.message_type == message_type]

    def get_text_messages(self) -> List[TextInteractionMessage]:
        """Get all text messages."""
        return [msg for msg in self.messages if isinstance(msg, TextInteractionMessage)]

    def get_media_messages(self) -> List[MediaInteractionMessage]:
        """Get all media messages."""
        return [
            msg for msg in self.messages if isinstance(msg, MediaInteractionMessage)
        ]

    def get_silent_messages(self) -> List[SilentInteractionMessage]:
        """Get all silent messages."""
        return [
            msg for msg in self.messages if isinstance(msg, SilentInteractionMessage)
        ]

    def get_multi_messages(self) -> List[MultiInteractionMessage]:
        """Get all multi messages."""
        return [
            msg for msg in self.messages if isinstance(msg, MultiInteractionMessage)
        ]

    async def search_messages(
        self,
        query: str,
        message_types: Optional[List[MessageType]] = None,
        date_range: Optional[tuple] = None,
    ) -> List[InteractionMessage]:
        """Search messages by content and criteria."""
        results = []
        query_lower = query.lower()

        for msg in self.messages:
            # Filter by type if specified
            if message_types and msg.message_type not in message_types:
                continue

            # Filter by date range if specified
            if date_range:
                start_date, end_date = date_range
                if not (start_date <= msg.timestamp <= end_date):
                    continue

            # Search content
            found = False
            if isinstance(msg, TextInteractionMessage):
                if query_lower in msg.text.lower():
                    found = True
            elif isinstance(msg, MediaInteractionMessage):
                found = (
                    bool(msg.caption and query_lower in msg.caption.lower())
                    or bool(
                        msg.media_content.filename
                        and query_lower in msg.media_content.filename.lower()
                    )
                )
            elif isinstance(msg, MultiInteractionMessage):
                # Search in sub-messages
                text_content = msg.get_text_content().lower()
                if query_lower in text_content:
                    found = True

            if found:
                results.append(msg)

        return results

    # ============== TOKEN MANAGEMENT ==============

    def update_token_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model_used: Optional[str] = None,
        cost_estimate: Optional[float] = None,
    ) -> None:
        """Update token usage statistics."""
        new_usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_used=model_used,
            cost_estimate=cost_estimate,
        )
        self.token_usage = self.token_usage.add_usage(new_usage)
        self.updated_at = datetime.now(timezone.utc)

    def get_token_summary(self) -> Dict[str, Any]:
        """Get token usage summary."""
        return {
            "input_tokens": self.token_usage.input_tokens,
            "output_tokens": self.token_usage.output_tokens,
            "total_tokens": self.token_usage.total_tokens,
            "cost_estimate": self.token_usage.cost_estimate,
            "model_used": self.token_usage.model_used,
        }

    # ============== ANALYTICS AND STATISTICS ==============

    async def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the response."""
        type_counts = {}
        total_size = 0
        total_word_count = 0

        for msg_type in MessageType:
            type_counts[msg_type.value] = len(self.get_messages_by_type(msg_type))

        for msg in self.messages:
            total_size += await msg.get_size()
            if isinstance(msg, TextInteractionMessage):
                total_word_count += msg.get_word_count()

        return {
            "interaction_id": self.interaction_id,
            "session_id": self.session_id,
            "total_messages": len(self.messages),
            "message_type_counts": type_counts,
            "total_size_bytes": total_size,
            "total_word_count": total_word_count,
            "token_usage": self.get_token_summary(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status,
        }

    async def get_content_summary(self) -> Dict[str, Any]:
        """Get a summary of the content."""
        text_messages = self.get_text_messages()
        media_messages = self.get_media_messages()

        summary = {
            "has_text": len(text_messages) > 0,
            "has_media": len(media_messages) > 0,
            "text_preview": "",
            "media_types": [],
        }

        # Generate text preview
        if text_messages:
            all_text = " ".join(msg.text for msg in text_messages)
            summary["text_preview"] = all_text[:200] + (
                "..." if len(all_text) > 200 else ""
            )

        # List media types
        media_types = set()
        for msg in media_messages:
            media_types.add(msg.media_content.media_type.value)
        summary["media_types"] = list(media_types)

        return summary

    # ============== SERIALIZATION AND PERSISTENCE ==============

    async def serialize(self) -> Dict[str, Any]:
        """Serialize the entire response."""
        serialized_messages = []
        for msg in self.messages:
            serialized_messages.append(await msg.serialize())

        return {
            "id": self.id,
            "interaction_id": self.interaction_id,
            "session_id": self.session_id,
            "messages": serialized_messages,
            "token_usage": {
                "input_tokens": self.token_usage.input_tokens,
                "output_tokens": self.token_usage.output_tokens,
                "total_tokens": self.token_usage.total_tokens,
                "cost_estimate": self.token_usage.cost_estimate,
                "model_used": self.token_usage.model_used,
            },
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status,
            "error_info": self.error_info,
        }

    @classmethod
    async def deserialize(cls, data: Dict[str, Any]) -> "InteractionResponse":
        """Deserialize a response from data."""
        try:
            response = cls(
                interaction_id=data["interaction_id"],
                session_id=data.get("session_id"),
                id=data.get("id"),
            )

            # Deserialize messages
            messages: List[InteractionMessage] = []
            for msg_data in data.get("messages", []):
                msg_type = MessageType(msg_data["message_type"])
                msg: InteractionMessage

                if msg_type == MessageType.SILENT:
                    msg = await SilentInteractionMessage.deserialize(msg_data)
                elif msg_type == MessageType.TEXT:
                    msg = await TextInteractionMessage.deserialize(msg_data)
                elif msg_type == MessageType.MEDIA:
                    msg = await MediaInteractionMessage.deserialize(msg_data)
                elif msg_type == MessageType.MULTI:
                    msg = await MultiInteractionMessage.deserialize(msg_data)
                else:
                    raise ValidationError(f"Unknown message type: {msg_type}")

                messages.append(msg)

            response.messages = messages

            # Deserialize token usage
            token_data = data.get("token_usage", {})
            response.token_usage = TokenUsage(
                input_tokens=token_data.get("input_tokens", 0),
                output_tokens=token_data.get("output_tokens", 0),
                total_tokens=token_data.get("total_tokens", 0),
                cost_estimate=token_data.get("cost_estimate"),
                model_used=token_data.get("model_used"),
            )

            # Set timestamps
            if "created_at" in data:
                response.created_at = datetime.fromisoformat(data["created_at"])
            if "updated_at" in data:
                response.updated_at = datetime.fromisoformat(data["updated_at"])

            response.status = data.get("status", "active")
            response.error_info = data.get("error_info")

            return response
        except Exception as e:
            raise ValidationError(f"Failed to deserialize InteractionResponse: {e}")

    # ============== VALIDATION AND HEALTH CHECKS ==============

    async def validate_response(self) -> bool:
        """Validate the entire response."""
        try:
            if not self.interaction_id:
                return False

            # Collect all validation results first
            validation_results = [await msg.validate() for msg in self.messages]
            return all(validation_results)
        except Exception:
            return False

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the response."""
        health: Dict[str, Any] = {
            "status": "healthy",
            "issues": [],  # type: ignore
            "warnings": []  # type: ignore
        }

        try:
            # Check if all messages are valid
            invalid_messages = []
            for msg in self.messages:
                if not await msg.validate():
                    invalid_messages.append(msg.message_id)

            if invalid_messages:
                health["issues"].append(
                    {"type": "invalid_messages", "message_ids": invalid_messages}
                )
                health["status"] = "degraded"

            # Check for unusually large messages
            large_messages = []
            for msg in self.messages:
                size = await msg.get_size()
                if size > 1024 * 1024:  # 1MB threshold
                    large_messages.append(
                        {
                            "message_id": msg.message_id,
                            "size_mb": round(size / (1024 * 1024), 2),
                        }
                    )

            if large_messages:
                health["warnings"].append(
                    {"type": "large_messages", "details": large_messages}
                )

            # Check token usage
            if self.token_usage.total_tokens > 100000:  # High token usage
                health["warnings"].append(
                    {
                        "type": "high_token_usage",
                        "total_tokens": self.token_usage.total_tokens,
                    }
                )

        except Exception as e:
            health["status"] = "unhealthy"
            health["issues"].append({"type": "health_check_error", "details": str(e)})

        return health

    # ============== UTILITY METHODS ==============

    async def clone(
        self, new_interaction_id: Optional[str] = None
    ) -> "InteractionResponse":
        """Create a copy of this response with a new ID."""
        serialized = await self.serialize()
        serialized["interaction_id"] = new_interaction_id or str(uuid.uuid4())
        serialized.pop("id", None)  # Remove ID to create new one
        return await self.deserialize(serialized)

    async def merge_with(self, other: "InteractionResponse") -> "InteractionResponse":
        """Merge this response with another response."""
        new_response = await self.clone()

        # Add all messages from the other response
        for msg in other.messages:
            await new_response.add_message(msg)

        # Merge token usage
        new_response.token_usage = new_response.token_usage.add_usage(other.token_usage)

        return new_response

    def set_error(self, error_info: str) -> None:
        """Set error information for the response."""
        self.error_info = error_info
        self.status = "error"
        self.updated_at = datetime.now(timezone.utc)

    def mark_completed(self) -> None:
        """Mark the response as completed."""
        self.status = "completed"
        self.updated_at = datetime.now(timezone.utc)

    def is_empty(self) -> bool:
        """Check if the response has no messages."""
        return len(self.messages) == 0

    def get_message_count(self) -> int:
        """Get the total number of messages."""
        return len(self.messages)
