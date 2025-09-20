"""MongoDB-style query parser and utilities.

Provides a unified query interface that translates MongoDB-style queries
into operations that can be executed on any database backend.
"""

import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union


class QueryOperator:
    """Enumeration of supported MongoDB-style query operators."""

    # Comparison operators
    EQ = "$eq"  # Equal
    NE = "$ne"  # Not equal
    GT = "$gt"  # Greater than
    GTE = "$gte"  # Greater than or equal
    LT = "$lt"  # Less than
    LTE = "$lte"  # Less than or equal
    IN = "$in"  # Value in array
    NIN = "$nin"  # Value not in array

    # Logical operators
    AND = "$and"  # Logical AND
    OR = "$or"  # Logical OR
    NOT = "$not"  # Logical NOT
    NOR = "$nor"  # Logical NOR

    # Element operators
    EXISTS = "$exists"  # Field exists
    TYPE = "$type"  # Field type check

    # Array operators
    SIZE = "$size"  # Array size
    ALL = "$all"  # All elements match
    ELEM_MATCH = "$elemMatch"  # Element matches condition

    # String operators
    REGEX = "$regex"  # Regular expression
    TEXT = "$text"  # Text search (simplified)

    # Evaluation operators
    WHERE = "$where"  # JavaScript expression (limited support)
    MOD = "$mod"  # Modulo operation


class QueryParser:
    """Parser for MongoDB-style queries."""

    @staticmethod
    def normalize_query(query: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a MongoDB-style query for consistent processing.

        Args:
            query: Raw MongoDB-style query

        Returns:
            Normalized query dictionary
        """
        if not query:
            return {}

        # Handle top-level logical operators
        if len(query) == 1 and list(query.keys())[0] in [
            QueryOperator.AND,
            QueryOperator.OR,
            QueryOperator.NOR,
        ]:
            return query

        # Convert implicit AND to explicit
        normalized = {}
        for key, value in query.items():
            if key.startswith("$"):
                # Top-level operator
                normalized[key] = value
            else:
                # Field condition
                normalized[key] = QueryParser._normalize_condition(value)

        return normalized

    @staticmethod
    def _normalize_condition(condition: Any) -> Any:
        """Normalize a single field condition."""
        if not isinstance(condition, dict):
            # Simple equality
            return {QueryOperator.EQ: condition}

        # Already an operator condition
        normalized = {}
        for op, value in condition.items():
            if op.startswith("$"):
                normalized[op] = value
            else:
                # Nested field - not an operator
                return {QueryOperator.EQ: condition}

        return normalized if normalized else {QueryOperator.EQ: condition}


FieldOperatorHandler = Callable[[Any, Any], bool]
LogicalOperatorHandler = Callable[[Dict[str, Any], Any], bool]


class DocumentMatcher:
    """Matches documents against MongoDB-style queries."""

    def __init__(self):
        self._field_operator_handlers: Dict[str, FieldOperatorHandler] = {
            QueryOperator.EQ: self._handle_eq,
            QueryOperator.NE: self._handle_ne,
            QueryOperator.GT: self._handle_gt,
            QueryOperator.GTE: self._handle_gte,
            QueryOperator.LT: self._handle_lt,
            QueryOperator.LTE: self._handle_lte,
            QueryOperator.IN: self._handle_in,
            QueryOperator.NIN: self._handle_nin,
            QueryOperator.EXISTS: self._handle_exists,
            QueryOperator.TYPE: self._handle_type,
            QueryOperator.SIZE: self._handle_size,
            QueryOperator.ALL: self._handle_all,
            QueryOperator.ELEM_MATCH: self._handle_elem_match,
            QueryOperator.REGEX: self._handle_regex,
            QueryOperator.MOD: self._handle_mod,
        }
        self._logical_operator_handlers: Dict[str, LogicalOperatorHandler] = {
            QueryOperator.AND: self._handle_and,
            QueryOperator.OR: self._handle_or,
            QueryOperator.NOT: self._handle_not,
            QueryOperator.NOR: self._handle_nor,
        }

    def matches(self, document: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if document matches query."""
        if not query:
            return True  # Empty query matches all documents

        normalized_query = QueryParser.normalize_query(query)
        return self._evaluate_query(document, normalized_query)

    def _evaluate_query(self, document: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Evaluate a normalized query against a document."""
        for field, condition in query.items():
            if field.startswith("$"):
                # Logical operator
                if not self._handle_logical_operator_dispatch(
                    document, field, condition
                ):
                    return False
            else:
                # Field condition
                if not self._evaluate_field_condition(document, field, condition):
                    return False
        return True

    def _evaluate_field_condition(
        self, document: Dict[str, Any], field: str, condition: Any
    ) -> bool:
        """Evaluate a condition against a specific field."""
        field_value = self._get_field_value(document, field)

        if isinstance(condition, dict):
            # Operator-based condition
            for operator, value in condition.items():
                handler = self._field_operator_handlers.get(operator)
                if handler and not handler(field_value, value):
                    return False
        else:
            # Simple equality (should be normalized to $eq)
            if field_value != condition:
                return False

        return True

    def _get_field_value(self, document: Dict[str, Any], field: str) -> Any:
        """Get value from document using dot notation."""
        if "." not in field:
            return document.get(field)

        keys = field.split(".")
        current: Optional[Any] = document

        for key in keys:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                try:
                    current = current[int(key)]
                except (IndexError, ValueError):
                    return None
            else:
                return None

        return current

    def _handle_logical_operator_dispatch(
        self, document: Dict[str, Any], operator: str, condition: Any
    ) -> bool:
        handler = self._logical_operator_handlers.get(operator)
        if handler:
            return handler(document, condition)
        return True

    # Comparison operators
    def _handle_eq(self, field_value: Any, condition_value: Any) -> bool:
        """Handle $eq operator."""
        return field_value == condition_value  # type: ignore[no-any-return]

    def _handle_ne(self, field_value: Any, condition_value: Any) -> bool:
        """Handle $ne operator."""
        return field_value != condition_value  # type: ignore[no-any-return]

    def _handle_gt(self, field_value: Any, condition_value: Any) -> bool:
        """Handle $gt operator."""
        if field_value is None:
            return False
        try:
            return field_value > condition_value  # type: ignore[no-any-return]
        except TypeError:
            return False

    def _handle_gte(self, field_value: Any, condition_value: Any) -> bool:
        """Handle $gte operator."""
        if field_value is None:
            return False
        try:
            return field_value >= condition_value  # type: ignore[no-any-return]
        except TypeError:
            return False

    def _handle_lt(self, field_value: Any, condition_value: Any) -> bool:
        """Handle $lt operator."""
        if field_value is None:
            return False
        try:
            return field_value < condition_value  # type: ignore[no-any-return]
        except TypeError:
            return False

    def _handle_lte(self, field_value: Any, condition_value: Any) -> bool:
        """Handle $lte operator."""
        if field_value is None:
            return False
        try:
            return field_value <= condition_value  # type: ignore[no-any-return]
        except TypeError:
            return False

    def _handle_in(self, field_value: Any, condition_value: List[Any]) -> bool:
        """Handle $in operator."""
        if not isinstance(condition_value, list):
            return False
        return field_value in condition_value

    def _handle_nin(self, field_value: Any, condition_value: List[Any]) -> bool:
        """Handle $nin operator."""
        if not isinstance(condition_value, list):
            return True
        return field_value not in condition_value

    # Element operators
    def _handle_exists(self, field_value: Any, condition_value: bool) -> bool:
        """Handle $exists operator."""
        field_exists = field_value is not None
        return field_exists == condition_value

    def _handle_type(self, field_value: Any, condition_value: Union[str, int]) -> bool:
        """Handle $type operator."""
        if field_value is None:
            return condition_value == "null" or condition_value == 10

        type_mapping = {
            1: "double",
            "double": 1,
            2: "string",
            "string": 2,
            3: "object",
            "object": 3,
            4: "array",
            "array": 4,
            8: "bool",
            "bool": 8,
            9: "date",
            "date": 9,
            10: "null",
            "null": 10,
            16: "int",
            "int": 16,
            18: "long",
            "long": 18,
        }

        actual_type = type(field_value).__name__
        if actual_type == "str":
            actual_type = "string"
        elif actual_type == "float":
            actual_type = "double"
        elif actual_type == "dict":
            actual_type = "object"
        elif actual_type == "list":
            actual_type = "array"
        elif isinstance(field_value, datetime):
            actual_type = "date"

        if isinstance(condition_value, str):
            return actual_type == condition_value
        else:
            return type_mapping.get(actual_type) == condition_value

    # Array operators
    def _handle_size(self, field_value: Any, condition_value: int) -> bool:
        """Handle $size operator."""
        if not isinstance(field_value, list):
            return False
        return len(field_value) == condition_value

    def _handle_all(self, field_value: Any, condition_value: List[Any]) -> bool:
        """Handle $all operator."""
        if not isinstance(field_value, list) or not isinstance(condition_value, list):
            return False
        return all(item in field_value for item in condition_value)

    def _handle_elem_match(
        self, field_value: Any, condition_value: Dict[str, Any]
    ) -> bool:
        """Handle $elemMatch operator."""
        if not isinstance(field_value, list):
            return False
        return any(
            self._evaluate_query(
                item if isinstance(item, dict) else {"value": item}, condition_value
            )
            for item in field_value
        )

    # String operators
    def _handle_regex(
        self, field_value: Any, condition_value: Union[str, Dict[str, Any]]
    ) -> bool:
        """Handle $regex operator."""
        if not isinstance(field_value, str):
            return False

        if isinstance(condition_value, dict):
            pattern = condition_value.get("$regex", "")
            options = condition_value.get("$options", "")
        else:
            pattern = str(condition_value)
            options = ""

        flags = 0
        if "i" in options:
            flags |= re.IGNORECASE
        if "m" in options:
            flags |= re.MULTILINE
        if "s" in options:
            flags |= re.DOTALL

        try:
            return bool(re.search(pattern, field_value, flags))
        except re.error:
            return False

    # Evaluation operators
    def _handle_mod(
        self, field_value: Any, condition_value: List[Union[int, float]]
    ) -> bool:
        """Handle $mod operator."""
        if not isinstance(condition_value, list) or len(condition_value) != 2:
            return False
        if not isinstance(field_value, (int, float)):
            return False

        divisor, remainder = condition_value
        if divisor == 0:
            return False

        return field_value % divisor == remainder

    # Logical operators (operate on document level)
    def _handle_and(
        self, document: Dict[str, Any], condition_value: List[Dict[str, Any]]
    ) -> bool:
        """Handle $and operator."""
        if not isinstance(condition_value, list):
            return False
        return all(self._evaluate_query(document, cond) for cond in condition_value)

    def _handle_or(
        self, document: Dict[str, Any], condition_value: List[Dict[str, Any]]
    ) -> bool:
        """Handle $or operator."""
        if not isinstance(condition_value, list):
            return False
        return any(self._evaluate_query(document, cond) for cond in condition_value)

    def _handle_not(
        self, document: Dict[str, Any], condition_value: Dict[str, Any]
    ) -> bool:
        """Handle $not operator."""
        if not isinstance(condition_value, dict):
            return False
        return not self._evaluate_query(document, condition_value)

    def _handle_nor(
        self, document: Dict[str, Any], condition_value: List[Dict[str, Any]]
    ) -> bool:
        """Handle $nor operator."""
        if not isinstance(condition_value, list):
            return False
        return not any(self._evaluate_query(document, cond) for cond in condition_value)


class QueryBuilder:
    """Builder for constructing MongoDB-style queries programmatically."""

    def __init__(self):
        self._query: Dict[str, Any] = {}

    def field(self, name: str) -> "FieldQuery":
        """Start a field query."""
        return FieldQuery(self, name)

    def and_(self, *conditions: Dict[str, Any]) -> "QueryBuilder":
        """Add AND condition."""
        if QueryOperator.AND not in self._query:
            self._query[QueryOperator.AND] = []
        self._query[QueryOperator.AND].extend(conditions)
        return self

    def or_(self, *conditions: Dict[str, Any]) -> "QueryBuilder":
        """Add OR condition."""
        if QueryOperator.OR not in self._query:
            self._query[QueryOperator.OR] = []
        self._query[QueryOperator.OR].extend(conditions)
        return self

    def nor(self, *conditions: Dict[str, Any]) -> "QueryBuilder":
        """Add NOR condition."""
        if QueryOperator.NOR not in self._query:
            self._query[QueryOperator.NOR] = []
        self._query[QueryOperator.NOR].extend(conditions)
        return self

    def build(self) -> Dict[str, Any]:
        """Build the final query."""
        return self._query.copy()

    def _add_field_condition(self, field: str, condition: Dict[str, Any]):
        """Add a field condition to the query."""
        if field in self._query:
            # Merge conditions for the same field
            if isinstance(self._query[field], dict) and isinstance(condition, dict):
                self._query[field].update(condition)
            else:
                # Convert to AND condition
                existing = self._query[field]
                self._query[field] = {QueryOperator.AND: [existing, condition]}
        else:
            self._query[field] = condition


class FieldQuery:
    """Field-specific query builder."""

    def __init__(self, parent: QueryBuilder, field_name: str):
        self._parent = parent
        self._field = field_name

    def eq(self, value: Any) -> QueryBuilder:
        """Equal to value."""
        self._parent._add_field_condition(self._field, {QueryOperator.EQ: value})
        return self._parent

    def ne(self, value: Any) -> QueryBuilder:
        """Not equal to value."""
        self._parent._add_field_condition(self._field, {QueryOperator.NE: value})
        return self._parent

    def gt(self, value: Any) -> QueryBuilder:
        """Greater than value."""
        self._parent._add_field_condition(self._field, {QueryOperator.GT: value})
        return self._parent

    def gte(self, value: Any) -> QueryBuilder:
        """Greater than or equal to value."""
        self._parent._add_field_condition(self._field, {QueryOperator.GTE: value})
        return self._parent

    def lt(self, value: Any) -> QueryBuilder:
        """Less than value."""
        self._parent._add_field_condition(self._field, {QueryOperator.LT: value})
        return self._parent

    def lte(self, value: Any) -> QueryBuilder:
        """Less than or equal to value."""
        self._parent._add_field_condition(self._field, {QueryOperator.LTE: value})
        return self._parent

    def in_(self, values: List[Any]) -> QueryBuilder:
        """Value in list."""
        self._parent._add_field_condition(self._field, {QueryOperator.IN: values})
        return self._parent

    def nin(self, values: List[Any]) -> QueryBuilder:
        """Value not in list."""
        self._parent._add_field_condition(self._field, {QueryOperator.NIN: values})
        return self._parent

    def exists(self, value: bool = True) -> QueryBuilder:
        """Field exists."""
        self._parent._add_field_condition(self._field, {QueryOperator.EXISTS: value})
        return self._parent

    def type_(self, type_name: Union[str, int]) -> QueryBuilder:
        """Field type check."""
        self._parent._add_field_condition(self._field, {QueryOperator.TYPE: type_name})
        return self._parent

    def size(self, length: int) -> QueryBuilder:
        """Array size check."""
        self._parent._add_field_condition(self._field, {QueryOperator.SIZE: length})
        return self._parent

    def all_(self, values: List[Any]) -> QueryBuilder:
        """All values present in array."""
        self._parent._add_field_condition(self._field, {QueryOperator.ALL: values})
        return self._parent

    def regex(self, pattern: str, options: str = "") -> QueryBuilder:
        """Regular expression match."""
        condition = {QueryOperator.REGEX: pattern}
        if options:
            condition["$options"] = options
        self._parent._add_field_condition(self._field, condition)
        return self._parent

    def mod(self, divisor: int, remainder: int) -> QueryBuilder:
        """Modulo operation."""
        self._parent._add_field_condition(
            self._field, {QueryOperator.MOD: [divisor, remainder]}
        )
        return self._parent


# Convenience function
def query() -> QueryBuilder:
    """Create a new query builder."""
    return QueryBuilder()


# Global matcher instance
_matcher = DocumentMatcher()


def matches_query(document: Dict[str, Any], query: Dict[str, Any]) -> bool:
    """Check if document matches MongoDB-style query.

    Args:
        document: Document to test
        query: MongoDB-style query

    Returns:
        True if document matches query
    """
    return _matcher.matches(document, query)
