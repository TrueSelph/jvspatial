"""MongoDB-style query parser and utilities with built-in optimization.

Provides a unified query interface that translates MongoDB-style queries
into operations that can be executed on any database backend.
Includes built-in query optimization for improved performance.
"""

import re
import time
from typing import Any, Callable, Dict, List, Optional, Union

# Unified evaluation and builder in a single module


class QueryEngine:
    """Unified MongoDB-style query engine with built-in optimization for all backends."""

    def __init__(self, enable_optimization: bool = True):
        """Initialize the query engine.

        Args:
            enable_optimization: Whether to enable built-in query optimization
        """
        self.enable_optimization = enable_optimization
        self._query_cache: Dict[str, Any] = {}
        self._optimization_stats = {
            "optimized_queries": 0,
            "cache_hits": 0,
            "optimization_time": 0.0,
        }

    def optimize_query(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize query for better performance.

        Args:
            query: Query dictionary to optimize

        Returns:
            Optimized query dictionary
        """
        if not self.enable_optimization:
            return query

        start_time = time.time()

        try:
            # Check query cache first
            query_key = str(sorted(query.items()))
            if query_key in self._query_cache:
                self._optimization_stats["cache_hits"] += 1
                return self._query_cache[query_key]

            # Apply optimizations
            optimized_query = query.copy()

            # Optimize AND clauses
            if "$and" in optimized_query:
                optimized_query["$and"] = self._optimize_and_clause(
                    optimized_query["$and"]
                )

            # Optimize field selection
            if "$select" in optimized_query:
                optimized_query["$select"] = self._optimize_field_selection(
                    optimized_query["$select"]
                )

            # Add indexing hints
            optimized_query = self._add_indexing_hints(optimized_query)

            # Cache the optimized query
            self._query_cache[query_key] = optimized_query

            # Update stats
            self._optimization_stats["optimized_queries"] += 1
            self._optimization_stats["optimization_time"] += time.time() - start_time

            return optimized_query

        except Exception:
            # If optimization fails, return original query
            return query

    def _optimize_and_clause(
        self, and_clause: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Optimize AND clauses for better performance.

        Args:
            and_clause: List of AND conditions

        Returns:
            Optimized AND clause list
        """
        # Sort by selectivity (more selective conditions first)
        return sorted(and_clause, key=self._get_selectivity_score, reverse=True)

    def _get_selectivity_score(self, condition: Dict[str, Any]) -> float:
        """Calculate selectivity score for a condition.

        Args:
            condition: Query condition

        Returns:
            Selectivity score (higher = more selective)
        """
        score = 0.0

        for field, value in condition.items():
            if field.startswith("$"):
                continue

            # Equality conditions are more selective
            if isinstance(value, (str, int, float, bool)):
                score += 1.0
            # Range conditions are moderately selective
            elif isinstance(value, dict) and any(
                op in value for op in ["$gt", "$lt", "$gte", "$lte"]
            ):
                score += 0.5
            # Array conditions are less selective
            elif isinstance(value, (list, dict)):
                score += 0.3

        return score

    def _optimize_field_selection(self, fields: List[str]) -> List[str]:
        """Optimize field selection for better performance.

        Args:
            fields: List of fields to select

        Returns:
            Optimized field list
        """
        # Remove duplicate fields
        unique_fields = list(dict.fromkeys(fields))

        # Sort fields by frequency of use (if we had usage stats)
        # For now, just return unique fields
        return unique_fields

    def _add_indexing_hints(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Add indexing hints to the query.

        Args:
            query: Query dictionary

        Returns:
            Query with indexing hints
        """
        # Add hints for common query patterns
        hints = []

        for field, value in query.items():
            if field.startswith("$"):
                continue

            # Add hint for equality or range conditions
            if isinstance(value, (str, int, float, bool)) or (
                isinstance(value, dict)
                and any(op in value for op in ["$gt", "$lt", "$gte", "$lte"])
            ):
                hints.append(field)

        if hints:
            query["$hint"] = hints

        return query

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get query optimization statistics.

        Returns:
            Optimization statistics dictionary
        """
        return self._optimization_stats.copy()

    def clear_query_cache(self) -> None:
        """Clear the query cache."""
        self._query_cache.clear()

    def reset_stats(self) -> None:
        """Reset optimization statistics."""
        self._optimization_stats = {
            "optimized_queries": 0,
            "cache_hits": 0,
            "optimization_time": 0.0,
        }

    @staticmethod
    def get_field_value(document: Dict[str, Any], field: str) -> Any:
        """Get a field value from a document, supporting dot notation.

        Args:
            document: Document to extract value from
            field: Field name, supports dot notation for nested fields

        Returns:
            Field value or None if not found
        """
        if not field:
            return None
        if "." not in field:
            return document.get(field)
        keys = field.split(".")
        current: Any = document
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list):
                try:
                    idx = int(key)
                except ValueError:
                    return None
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
        return current

    @staticmethod
    def set_field_value(document: Dict[str, Any], field: str, value: Any) -> None:
        """Set a field value in a document, supporting dot notation.

        Args:
            document: Document to modify
            field: Field name, supports dot notation for nested fields
            value: Value to set
        """
        if not field:
            return
        keys = field.split(".")
        current: Any = document
        for key in keys[:-1]:
            if isinstance(current, list):
                idx = int(key)
                while idx >= len(current):
                    current.append({})
                if not isinstance(current[idx], dict):
                    current[idx] = {}
                current = current[idx]
            else:
                if key not in current or not isinstance(current[key], dict):
                    current[key] = {}
                current = current[key]
        last = keys[-1]
        if isinstance(current, list):
            idx = int(last)
            while idx >= len(current):
                current.append(None)
            current[idx] = value
        else:
            current[last] = value

    @staticmethod
    def unset_field_value(document: Dict[str, Any], field: str) -> None:
        """Remove a field value from a document, supporting dot notation.

        Args:
            document: Document to modify
            field: Field name, supports dot notation for nested fields
        """
        if not field:
            return
        keys = field.split(".")
        current: Any = document
        for key in keys[:-1]:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    current = current[int(key)]
                except Exception:
                    return
            else:
                return
            if current is None:
                return
        last = keys[-1]
        if isinstance(current, list):
            try:
                current[int(last)] = None
            except Exception:
                return
        elif isinstance(current, dict):
            current.pop(last, None)

    @staticmethod
    def match(document: Dict[str, Any], query: Optional[Dict[str, Any]]) -> bool:
        """Check if a document matches a query.

        Args:
            document: Document to check
            query: Query conditions

        Returns:
            True if document matches query, False otherwise
        """
        if not query:
            return True
        for key, condition in query.items():
            if key == "$and":
                if not all(QueryEngine.match(document, sub) for sub in condition or []):
                    return False
            elif key == "$or":
                if not any(QueryEngine.match(document, sub) for sub in condition or []):
                    return False
            elif key == "$not":
                if QueryEngine.match(document, condition):
                    return False
            else:
                value = QueryEngine.get_field_value(document, key)
                if not QueryEngine._match_value(value, condition):
                    return False
        return True

    @staticmethod
    def _match_value(value: Any, condition: Any) -> bool:
        if not isinstance(condition, dict):
            return value == condition  # type: ignore[no-any-return]

        for op, operand in condition.items():
            if op == "$eq":
                if value != operand:
                    return False
            elif op == "$ne":
                if value == operand:
                    return False
            elif op == "$gt":
                if not (value is not None and value > operand):
                    return False
            elif op == "$gte":
                if not (value is not None and value >= operand):
                    return False
            elif op == "$lt":
                if not (value is not None and value < operand):
                    return False
            elif op == "$lte":
                if not (value is not None and value <= operand):
                    return False
            elif op == "$in":
                try:
                    if value not in operand:
                        return False
                except TypeError:
                    return False
            elif op == "$nin":
                try:
                    if value in operand:
                        return False
                except TypeError:
                    return False
            elif op == "$exists":
                exists = value is not None
                if bool(operand) != exists:
                    return False
            elif op == "$regex":
                if value is None or not isinstance(value, str):
                    return False
                pattern = operand
                flags = 0
                if isinstance(operand, dict):
                    pattern = operand.get("pattern", "")
                    if operand.get("ignoreCase"):
                        flags |= re.IGNORECASE
                try:
                    if re.search(pattern, value, flags) is None:
                        return False
                except re.error:
                    return False
            elif op == "$size":
                try:
                    if len(value) != int(operand):
                        return False
                except Exception:
                    return False
            elif op == "$elemMatch":
                if not isinstance(value, list):
                    return False
                if not any(
                    (
                        QueryEngine._match_value(elem, operand)
                        if not isinstance(operand, dict)
                        else QueryEngine.match(
                            elem if isinstance(elem, dict) else {"_": elem}, operand
                        )
                    )
                    for elem in value
                ):
                    return False
            else:
                return False
        return True

    @staticmethod
    def apply_update(
        document: Dict[str, Any], update: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply update operations to a document.

        Args:
            document: Document to update
            update: Update operations to apply

        Returns:
            Updated document
        """
        if not update:
            return document
        for op, payload in update.items():
            if op == "$set":
                for field, value in payload.items():
                    QueryEngine.set_field_value(document, field, value)
            elif op == "$unset":
                for field in payload.keys():
                    QueryEngine.unset_field_value(document, field)
            elif op == "$inc":
                for field, inc_value in payload.items():
                    current = QueryEngine.get_field_value(document, field) or 0
                    QueryEngine.set_field_value(document, field, current + inc_value)
            elif op == "$push":
                for field, item in payload.items():
                    arr = QueryEngine.get_field_value(document, field)
                    if not isinstance(arr, list):
                        arr = []
                    arr = list(arr)
                    arr.append(item)
                    QueryEngine.set_field_value(document, field, arr)
            elif op == "$addToSet":
                for field, item in payload.items():
                    arr = QueryEngine.get_field_value(document, field)
                    if not isinstance(arr, list):
                        arr = []
                    arr = list(arr)
                    if item not in arr:
                        arr.append(item)
                    QueryEngine.set_field_value(document, field, arr)
            else:
                continue
        return document


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


FieldOperatorHandler = Callable[[Any, Any], bool]
LogicalOperatorHandler = Callable[[Dict[str, Any], Any], bool]


class QueryBuilder:
    """Builder for constructing MongoDB-style queries programmatically."""

    def __init__(self):
        self._query: Dict[str, Any] = {}

    def field(self, name: str) -> "FieldQuery":
        """Start a field query."""
        return FieldQuery(self, name)

    def and_(
        self, *conditions: Union[Dict[str, Any], List[Dict[str, Any]]]
    ) -> "QueryBuilder":
        """Add AND condition."""
        if QueryOperator.AND not in self._query:
            self._query[QueryOperator.AND] = []

        # Handle both single conditions and lists of conditions
        for condition in conditions:
            if isinstance(condition, list):
                self._query[QueryOperator.AND].extend(condition)
            else:
                self._query[QueryOperator.AND].append(condition)
        return self

    def or_(self, *conditions: Dict[str, Any]) -> "QueryBuilder":
        """Add OR condition."""
        if QueryOperator.OR not in self._query:
            self._query[QueryOperator.OR] = []
        self._query[QueryOperator.OR].extend(conditions)
        return self

    def nor_(self, *conditions: Dict[str, Any]) -> "QueryBuilder":
        """Add NOR condition."""
        if QueryOperator.NOR not in self._query:
            self._query[QueryOperator.NOR] = []
        self._query[QueryOperator.NOR].extend(conditions)
        return self

    def build(self) -> Dict[str, Any]:
        """Build the final query."""
        result = {}
        for key, value in self._query.items():
            # Only include non-empty logical operators
            if key in [QueryOperator.AND, QueryOperator.OR, QueryOperator.NOR]:
                if value:  # Only include if not empty
                    result[key] = value
            else:
                result[key] = value
        return result

    def _add_field_condition(self, field: str, condition: Dict[str, Any]):
        """Add a field condition to the query."""
        if field in self._query:
            # Merge conditions for the same field
            if isinstance(self._query[field], dict) and isinstance(condition, dict):
                # Check if we're adding a new operator to the same field
                for op, value in condition.items():
                    if op in self._query[field]:
                        # If operator already exists, convert to AND condition
                        existing = self._query[field][op]
                        self._query[field][op] = {QueryOperator.AND: [existing, value]}
                    else:
                        self._query[field][op] = value
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

    def eq(self, value: Any) -> "FieldQuery":
        """Equal to value."""
        self._parent._add_field_condition(self._field, {QueryOperator.EQ: value})
        return self

    def ne(self, value: Any) -> "FieldQuery":
        """Not equal to value."""
        self._parent._add_field_condition(self._field, {QueryOperator.NE: value})
        return self

    def gt(self, value: Any) -> "FieldQuery":
        """Greater than value."""
        self._parent._add_field_condition(self._field, {QueryOperator.GT: value})
        return self

    def gte(self, value: Any) -> "FieldQuery":
        """Greater than or equal to value."""
        self._parent._add_field_condition(self._field, {QueryOperator.GTE: value})
        return self

    def lt(self, value: Any) -> "FieldQuery":
        """Less than value."""
        self._parent._add_field_condition(self._field, {QueryOperator.LT: value})
        return self

    def lte(self, value: Any) -> "FieldQuery":
        """Less than or equal to value."""
        self._parent._add_field_condition(self._field, {QueryOperator.LTE: value})
        return self

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
