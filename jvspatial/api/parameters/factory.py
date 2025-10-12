"""Factory for creating parameter models from Walker classes."""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Type, cast

from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.fields import FieldInfo, PydanticUndefined

from jvspatial.core.entities import Walker

from .metadata import build_field_config, extract_field_metadata
from .model import EndpointParameterModel


class ParameterModelFactory:
    """Factory for creating parameter models from Walker classes using Field metadata."""

    @classmethod
    def create_model(
        cls: Type["ParameterModelFactory"],
        walker_cls: Type[Walker],
    ) -> Type[BaseModel]:
        """Create parameter model for a Walker class.

        Args:
            walker_cls: Walker class to create model for

        Returns:
            Generated parameter model
        """
        fields: Dict[str, Tuple[Any, Any]] = {}
        grouped_fields = defaultdict(list)

        # Walker base fields that should be excluded
        walker_base_fields = {"id", "queue", "response", "current_node", "paused"}

        for name, field_info in walker_cls.model_fields.items():
            endpoint_config = extract_field_metadata(field_info)

            # Skip base fields and excluded fields
            if (
                name in walker_base_fields and not endpoint_config
            ) or endpoint_config.get("exclude_endpoint", False):
                continue

            # Build field config
            param_name = endpoint_config.get("endpoint_name") or name
            field_tuple = cls._build_field(name, field_info, endpoint_config)

            # Handle field grouping
            group = endpoint_config.get("endpoint_group")
            if group:
                grouped_fields[group].append((param_name, field_tuple))
            else:
                fields[param_name] = field_tuple

        # Create nested models for grouped fields
        for group_name, group_fields in grouped_fields.items():
            if group_fields:
                group_model = cls._create_group_model(group_name, group_fields)
                fields[group_name] = (Optional[group_model], Field(default=None))  # type: ignore[assignment]

        # Create the parameter model
        model_name = f"{walker_cls.__name__}ParameterModel"
        model = cast(
            Type[BaseModel],
            create_model(
                model_name,
                __base__=EndpointParameterModel,
                __config__=ConfigDict(extra="forbid"),
                **fields,
            ),
        )
        return model

    @classmethod
    def _build_field(
        cls: Type["ParameterModelFactory"],
        name: str,
        field_info: FieldInfo,
        endpoint_config: Dict[str, Any],
    ) -> Tuple[Type, FieldInfo]:
        """Build a parameter field.

        Args:
            name: Original field name
            field_info: Original field info
            endpoint_config: Endpoint configuration

        Returns:
            Tuple of (field_type, field_info)
        """
        # Get original type and default
        field_type = field_info.annotation
        default = field_info.default

        # Handle endpoint-specific required override
        if endpoint_config.get("endpoint_required") is not None:
            if endpoint_config["endpoint_required"]:
                if default is None:
                    default = PydanticUndefined
            else:
                if not cls._is_optional(field_type):
                    field_type = Optional[field_type]
                if default is PydanticUndefined:
                    default = None

        # Build field config
        config = build_field_config(field_info, endpoint_config)
        return (field_type, Field(default=default, **config))

    @classmethod
    def _create_group_model(
        cls: Type["ParameterModelFactory"],
        group_name: str,
        group_fields: List[Tuple[str, Tuple[Type, FieldInfo]]],
    ) -> Type[BaseModel]:
        """Create a model for grouped fields.

        Args:
            group_name: Name of the group
            group_fields: List of fields in the group

        Returns:
            Model class for the group
        """
        fields = dict(group_fields)
        model_name = f"{group_name.title()}Group"
        return cast(
            Type[BaseModel],
            create_model(
                model_name,
                __config__=ConfigDict(extra="forbid"),
                **fields,
            ),
        )

    @staticmethod
    def _is_optional(field_type: Type) -> bool:
        """Check if a type is Optional.

        Args:
            field_type: Type to check

        Returns:
            True if the type is Optional
        """
        return (
            hasattr(field_type, "__origin__")
            and field_type.__origin__ is Optional
            and type(None) in field_type.__args__
        )
