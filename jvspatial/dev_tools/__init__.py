"""Development tools for schema generation and validation.

This module provides comprehensive development tools for jvspatial applications,
including schema generation, validation, and development utilities.
"""

import json
import logging
from typing import Any, Dict, List, Type, Union

from jvspatial.core.entities import Object


class SchemaGenerator:
    """Schema generator for jvspatial entities.

    Generates JSON schemas for entities, walkers, and API endpoints
    to aid in development and documentation.
    """

    def __init__(self):
        """Initialize the schema generator."""
        self._logger = logging.getLogger(__name__)

    def generate_entity_schema(self, entity_class: Type[Object]) -> Dict[str, Any]:
        """Generate JSON schema for an entity class.

        Args:
            entity_class: Entity class to generate schema for

        Returns:
            JSON schema dictionary
        """
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": entity_class.__name__,
            "description": getattr(entity_class, "__doc__", "").strip(),
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }

        # Get model fields if available (Pydantic model)
        if hasattr(entity_class, "model_fields"):
            for field_name, field_info in entity_class.model_fields.items():
                field_schema = self._convert_field_to_schema(field_info)
                schema["properties"][field_name] = field_schema

                if field_info.is_required():
                    schema["required"].append(field_name)

        # Get class attributes for non-Pydantic classes
        elif hasattr(entity_class, "__annotations__"):
            for field_name, field_type in entity_class.__annotations__.items():
                if not field_name.startswith("_"):
                    field_schema = self._convert_type_to_schema(field_type)
                    schema["properties"][field_name] = field_schema

        return schema

    def _convert_field_to_schema(self, field_info) -> Dict[str, Any]:
        """Convert Pydantic field info to JSON schema.

        Args:
            field_info: Pydantic field information

        Returns:
            JSON schema for the field
        """
        schema = {}

        # Get field type
        field_type = field_info.annotation

        # Convert type to schema
        schema.update(self._convert_type_to_schema(field_type))

        # Add field description
        if field_info.description:
            schema["description"] = field_info.description

        # Add default value
        if field_info.default is not None:
            schema["default"] = field_info.default

        return schema

    def _convert_type_to_schema(self, field_type: Type) -> Dict[str, Any]:
        """Convert Python type to JSON schema.

        Args:
            field_type: Python type annotation

        Returns:
            JSON schema for the type
        """
        import typing  # noqa: F401

        # Handle Union types
        if hasattr(field_type, "__origin__") and field_type.__origin__ is Union:
            return {
                "oneOf": [
                    self._convert_type_to_schema(arg) for arg in field_type.__args__
                ]
            }

        # Handle Optional types
        if hasattr(field_type, "__origin__") and field_type.__origin__ is Union:
            args = field_type.__args__
            if len(args) == 2 and type(None) in args:
                non_none_type = args[0] if args[1] is type(None) else args[1]
                schema = self._convert_type_to_schema(non_none_type)
                schema["nullable"] = True
                return schema

        # Handle List types
        if hasattr(field_type, "__origin__") and field_type.__origin__ is list:
            return {
                "type": "array",
                "items": (
                    self._convert_type_to_schema(field_type.__args__[0])
                    if field_type.__args__
                    else {}
                ),
            }

        # Handle Dict types
        if hasattr(field_type, "__origin__") and field_type.__origin__ is dict:
            return {"type": "object", "additionalProperties": True}

        # Handle basic types
        type_mapping = {
            str: {"type": "string"},
            int: {"type": "integer"},
            float: {"type": "number"},
            bool: {"type": "boolean"},
            type(None): {"type": "null"},
        }

        return type_mapping.get(field_type, {"type": "string"})

    def generate_api_schema(self, endpoints: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate OpenAPI schema for API endpoints.

        Args:
            endpoints: List of endpoint definitions

        Returns:
            OpenAPI schema dictionary
        """
        schema = {
            "openapi": "3.0.0",
            "info": {
                "title": "jvspatial API",
                "version": "1.0.0",
                "description": "API built with jvspatial framework",
            },
            "paths": {},
            "components": {
                "schemas": {},
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT",
                    },
                    "apiKeyAuth": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-API-Key",
                    },
                },
            },
        }

        for endpoint in endpoints:
            path = endpoint.get("path", "")
            methods = endpoint.get("methods", ["POST"])
            handler = endpoint.get("handler")  # noqa: F841

            if path not in schema["paths"]:
                schema["paths"][path] = {}

            for method in methods:
                method_lower = method.lower()
                schema["paths"][path][method_lower] = self._generate_endpoint_schema(
                    endpoint
                )

        return schema

    def _generate_endpoint_schema(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """Generate schema for a single endpoint.

        Args:
            endpoint: Endpoint definition

        Returns:
            OpenAPI operation schema
        """
        operation = {
            "summary": endpoint.get("summary", ""),
            "description": endpoint.get("description", ""),
            "responses": {
                "200": {
                    "description": "Successful response",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "success": {"type": "boolean"},
                                    "data": {"type": "object"},
                                },
                            }
                        }
                    },
                }
            },
        }

        # Add security if required
        if endpoint.get("auth_required", False):
            operation["security"] = [{"bearerAuth": []}, {"apiKeyAuth": []}]

        return operation


class GraphValidator:
    """Validator for graph structure and operations.

    Provides validation for graph data, entity relationships,
    and graph operations to ensure data integrity.
    """

    def __init__(self):
        """Initialize the graph validator."""
        self._logger = logging.getLogger(__name__)

    def validate_graph_structure(self, graph_data: Dict[str, Any]) -> List[str]:
        """Validate graph structure and return any issues.

        Args:
            graph_data: Graph data to validate

        Returns:
            List of validation issues (empty if valid)
        """
        issues = []

        # Validate nodes
        if "nodes" in graph_data:
            issues.extend(self._validate_nodes(graph_data["nodes"]))

        # Validate edges
        if "edges" in graph_data:
            issues.extend(self._validate_edges(graph_data["edges"]))

        # Validate walkers
        if "walkers" in graph_data:
            issues.extend(self._validate_walkers(graph_data["walkers"]))

        return issues

    def _validate_nodes(self, nodes: List[Dict[str, Any]]) -> List[str]:
        """Validate node data.

        Args:
            nodes: List of node data

        Returns:
            List of validation issues
        """
        issues = []
        node_ids = set()

        for i, node in enumerate(nodes):
            # Check required fields
            if "id" not in node:
                issues.append(f"Node {i}: Missing required field 'id'")
                continue

            node_id = node["id"]

            # Check for duplicate IDs
            if node_id in node_ids:
                issues.append(f"Node {i}: Duplicate ID '{node_id}'")
            else:
                node_ids.add(node_id)

            # Validate ID format
            if not self._is_valid_entity_id(node_id):
                issues.append(f"Node {i}: Invalid ID format '{node_id}'")

        return issues

    def _validate_edges(self, edges: List[Dict[str, Any]]) -> List[str]:
        """Validate edge data.

        Args:
            edges: List of edge data

        Returns:
            List of validation issues
        """
        issues = []

        for i, edge in enumerate(edges):
            # Check required fields
            required_fields = ["id", "source", "target"]
            for field in required_fields:
                if field not in edge:
                    issues.append(f"Edge {i}: Missing required field '{field}'")

            # Validate ID format
            if "id" in edge and not self._is_valid_entity_id(edge["id"]):
                issues.append(f"Edge {i}: Invalid ID format '{edge['id']}'")

            # Validate source and target IDs
            if "source" in edge and not self._is_valid_entity_id(edge["source"]):
                issues.append(f"Edge {i}: Invalid source ID format '{edge['source']}'")

            if "target" in edge and not self._is_valid_entity_id(edge["target"]):
                issues.append(f"Edge {i}: Invalid target ID format '{edge['target']}'")

        return issues

    def _validate_walkers(self, walkers: List[Dict[str, Any]]) -> List[str]:
        """Validate walker data.

        Args:
            walkers: List of walker data

        Returns:
            List of validation issues
        """
        issues = []
        walker_ids = set()

        for i, walker in enumerate(walkers):
            # Check required fields
            if "id" not in walker:
                issues.append(f"Walker {i}: Missing required field 'id'")
                continue

            walker_id = walker["id"]

            # Check for duplicate IDs
            if walker_id in walker_ids:
                issues.append(f"Walker {i}: Duplicate ID '{walker_id}'")
            else:
                walker_ids.add(walker_id)

            # Validate ID format
            if not self._is_valid_entity_id(walker_id):
                issues.append(f"Walker {i}: Invalid ID format '{walker_id}'")

        return issues

    def _is_valid_entity_id(self, entity_id: str) -> bool:
        """Check if entity ID has valid format.

        Args:
            entity_id: Entity ID to validate

        Returns:
            True if valid format, False otherwise
        """
        # Basic format validation: type:EntityType:id
        parts = entity_id.split(":")
        return len(parts) == 3 and all(part for part in parts)


class DevelopmentTools:
    """Comprehensive development tools for jvspatial applications."""

    def __init__(self):
        """Initialize development tools."""
        self.schema_generator = SchemaGenerator()
        self.graph_validator = GraphValidator()
        self._logger = logging.getLogger(__name__)

    def generate_entity_documentation(self, entity_class: Type[Object]) -> str:
        """Generate documentation for an entity class.

        Args:
            entity_class: Entity class to document

        Returns:
            Markdown documentation string
        """
        schema = self.schema_generator.generate_entity_schema(entity_class)

        doc = f"# {entity_class.__name__}\n\n"

        if schema.get("description"):
            doc += f"{schema['description']}\n\n"

        doc += "## Properties\n\n"

        for prop_name, prop_schema in schema.get("properties", {}).items():
            doc += f"### {prop_name}\n\n"

            if prop_schema.get("description"):
                doc += f"{prop_schema['description']}\n\n"

            doc += f"- **Type**: {prop_schema.get('type', 'unknown')}\n"

            if prop_name in schema.get("required", []):
                doc += "- **Required**: Yes\n"
            else:
                doc += "- **Required**: No\n"

            if "default" in prop_schema:
                doc += f"- **Default**: {prop_schema['default']}\n"

            doc += "\n"

        return doc

    def validate_graph_data(self, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate graph data and return validation results.

        Args:
            graph_data: Graph data to validate

        Returns:
            Validation results dictionary
        """
        issues = self.graph_validator.validate_graph_structure(graph_data)

        return {"valid": len(issues) == 0, "issues": issues, "issue_count": len(issues)}

    def generate_api_documentation(self, endpoints: List[Dict[str, Any]]) -> str:
        """Generate API documentation from endpoints.

        Args:
            endpoints: List of endpoint definitions

        Returns:
            Markdown API documentation
        """
        doc = "# API Documentation\n\n"

        for endpoint in endpoints:
            path = endpoint.get("path", "")
            methods = endpoint.get("methods", ["POST"])
            summary = endpoint.get("summary", "")
            description = endpoint.get("description", "")

            doc += f"## {path}\n\n"

            if summary:
                doc += f"**{summary}**\n\n"

            if description:
                doc += f"{description}\n\n"

            doc += f"**Methods**: {', '.join(methods)}\n\n"

            if endpoint.get("auth_required", False):
                doc += "**Authentication**: Required\n\n"

            doc += "---\n\n"

        return doc

    def export_schema(self, entity_class: Type[Object], file_path: str) -> None:
        """Export entity schema to JSON file.

        Args:
            entity_class: Entity class to export schema for
            file_path: Path to save schema file
        """
        schema = self.schema_generator.generate_entity_schema(entity_class)

        with open(file_path, "w") as f:
            json.dump(schema, f, indent=2)

        self._logger.info(f"Exported schema for {entity_class.__name__} to {file_path}")


__all__ = ["SchemaGenerator", "GraphValidator", "DevelopmentTools"]
