"""Bounded host declarations for optional rich graph captures."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _path(value: str) -> str:
    if (
        not value
        or len(value) > 128
        or any(not part.isidentifier() for part in value.split("."))
    ):
        raise ValueError(
            "field paths require dotted identifiers of at most 128 characters"
        )
    return value


class ProjectionEvidence(BaseModel):
    """Same-record paths supplying recorded provenance, never verified authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_path: Optional[str] = None
    observed_at_path: Optional[str] = None
    verification_path: Optional[str] = None
    revision_path: Optional[str] = None
    confidence_path: Optional[str] = None

    @field_validator(
        "source_path",
        "observed_at_path",
        "verification_path",
        "revision_path",
        "confidence_path",
    )
    @classmethod
    def validate_path(cls, value: Optional[str]) -> Optional[str]:
        """Validate exact relative context paths."""
        return _path(value) if value is not None else None


class ProjectionField(BaseModel):
    """An exact context path with descriptive hints and optional tighter caps."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str
    label: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1024)
    data_type: Optional[str] = Field(default=None, max_length=64)
    unit: Optional[str] = Field(default=None, max_length=64)
    priority: int = Field(default=0, ge=0, le=1000)
    max_string: Optional[int] = Field(default=None, ge=1, le=4096)
    max_items: Optional[int] = Field(default=None, ge=1, le=100)
    max_value_depth: Optional[int] = Field(default=None, ge=0, le=10)
    evidence: Optional[ProjectionEvidence] = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """Reject wildcard and malformed paths."""
        return _path(value)


class ProjectionContextConfig(BaseModel):
    """Host-selected per-discriminator detail profiles; declarations grant no access."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    profile_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    revision: Optional[str] = Field(default=None, min_length=1, max_length=128)
    node_fields: Dict[str, Tuple[ProjectionField, ...]] = Field(default_factory=dict)
    edge_fields: Dict[str, Tuple[ProjectionField, ...]] = Field(default_factory=dict)

    @field_validator("node_fields", "edge_fields")
    @classmethod
    def validate_fields(
        cls, value: Dict[str, Tuple[ProjectionField, ...]]
    ) -> Dict[str, Tuple[ProjectionField, ...]]:
        """Bound type/field counts and reject duplicate paths."""
        if len(value) > 64:
            raise ValueError("profiles allow at most 64 types")
        for entity, fields in value.items():
            if not entity or len(entity) > 128 or len(fields) > 32:
                raise ValueError(
                    "profiles require bounded type names and at most 32 fields"
                )
            if len({field.path for field in fields}) != len(fields):
                raise ValueError("duplicate profile field path")
        return value

    @model_validator(mode="after")
    def validate_size(self) -> ProjectionContextConfig:
        """Bound aggregate declaration storage before capture."""
        if len(self.model_dump_json().encode()) > 65536:
            raise ValueError("context configuration exceeds 65536 bytes")
        return self


class ProjectionRelation(BaseModel):
    """Application-declared relationship meaning selected from captured facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=128)
    edge_type: str = Field(min_length=1, max_length=128)
    description: str = Field(max_length=1024)
    direction: str = Field(min_length=1, max_length=256)
    inverse: Optional[str] = Field(default=None, max_length=256)
    conditions: Optional[str] = Field(default=None, max_length=1024)
    edge_filter: Dict[str, Any] = Field(default_factory=dict)
    source_filter: Dict[str, Any] = Field(default_factory=dict)
    target_filter: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("edge_filter", "source_filter", "target_filter")
    @classmethod
    def validate_filter(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        """Use the projection's bounded predicate contract and exact field paths."""
        from .graph_projection import _query_fields

        if len(json.dumps(value, allow_nan=False).encode()) > 8192:
            raise ValueError("relation selector exceeds 8192 bytes")
        for field in _query_fields(value):
            if field not in ("id", "entity"):
                if not field.startswith("context."):
                    raise ValueError(
                        "selectors require context paths or intrinsic identity"
                    )
                _path(field[8:])
        return value
