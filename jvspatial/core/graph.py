"""Graph visualization utilities for generating renderable graph representations.

This module provides utilities for generating graph visualizations in various formats
including DOT (Graphviz) and Mermaid notation, suitable for documentation, debugging,
and graph analysis.

Usage:
    from jvspatial.core.context import get_default_context
    from jvspatial.core.graph import generate_graph_dot, generate_graph_mermaid

    context = get_default_context()

    # Generate DOT format (Graphviz)
    dot_graph = await generate_graph_dot(context)

    # Generate Mermaid format
    mermaid_graph = await generate_graph_mermaid(context)
"""

from typing import Any, Callable, Dict, List, Optional

from .context import GraphContext


async def generate_graph_dot(
    context: GraphContext,
    include_attributes: bool = True,
    node_filter: Optional[Callable[[Dict[str, Any]], bool]] = None,
    edge_filter: Optional[Callable[[Dict[str, Any]], bool]] = None,
    node_attributes: Optional[List[str]] = None,
    edge_attributes: Optional[List[str]] = None,
    graph_name: str = "jvspatial_graph",
    rankdir: str = "TB",
    node_shape: str = "box",
    style_options: Optional[Dict[str, Any]] = None,
    output_file: Optional[str] = None,
) -> str:
    """Generate a DOT (Graphviz) representation of the graph.

    Args:
        context: GraphContext instance for accessing graph data
        include_attributes: Whether to include node/edge attributes as labels
        node_filter: Optional function to filter nodes (receives node dict, returns bool)
        edge_filter: Optional function to filter edges (receives edge dict, returns bool)
        node_attributes: List of node attributes to include in label (None = all)
        edge_attributes: List of edge attributes to include in label (None = all)
        graph_name: Name of the graph in DOT format
        rankdir: Graph direction: TB (top-bottom), LR (left-right), BT (bottom-top), RL (right-left)
        node_shape: Shape for nodes: box, ellipse, circle, diamond, etc.
        style_options: Additional style options for the graph

    Returns:
        DOT format string suitable for rendering with Graphviz

    Keyword Args:
        output_file: Optional file path to save the DOT output. If provided, the graph
                    will be written to this file in addition to being returned.

    Example:
        ```python
        from jvspatial.core.context import get_default_context
        from jvspatial.core.graph import generate_graph_dot

        context = get_default_context()
        dot = await generate_graph_dot(
            context,
            rankdir="LR",
            node_shape="ellipse"
        )
        print(dot)
        ```
    """
    # Get all nodes and edges from database
    nodes_data = await context.database.find("node", {})
    edges_data = await context.database.find("edge", {})

    # Apply filters if provided
    if node_filter:
        nodes_data = [n for n in nodes_data if node_filter(n)]
    if edge_filter:
        edges_data = [e for e in edges_data if edge_filter(e)]

    # Build node set from edges to ensure all referenced nodes are included
    referenced_node_ids = set()
    for edge in edges_data:
        referenced_node_ids.add(edge.get("source"))
        referenced_node_ids.add(edge.get("target"))

    # Start DOT graph
    lines = [f"digraph {graph_name} {{"]

    # Add graph-level attributes
    lines.append(f"  rankdir={rankdir};")
    if style_options:
        for key, value in style_options.items():
            lines.append(f'  {key}="{value}";')

    # Process nodes
    for node_data in nodes_data:
        node_id = node_data.get("id", "")
        node_name = node_data.get("name", "Unknown")
        context_data = node_data.get("context", {})

        # Skip if node is not referenced and filter is strict
        if node_id not in referenced_node_ids and not any(
            n.get("id") == node_id for n in nodes_data
        ):
            continue

        # Build node label
        node_label = _build_node_label(
            node_name, node_id, context_data, include_attributes, node_attributes
        )

        # Create node statement
        node_attrs = [f'label="{_escape_dot_string(node_label)}"']
        node_attrs.append(f"shape={node_shape}")

        # Add custom styling based on node properties
        if node_data.get("is_root"):
            node_attrs.append('style="bold,filled"')
            node_attrs.append('fillcolor="lightblue"')

        lines.append(f'  "{_escape_dot_string(node_id)}" [{",".join(node_attrs)}];')

    # Process edges
    for edge_data in edges_data:
        source = edge_data.get("source")
        target = edge_data.get("target")
        bidirectional = edge_data.get("bidirectional", False)
        context_data = edge_data.get("context", {})

        if not source or not target:
            continue

        # Build edge label
        edge_label = _build_edge_label(
            context_data, include_attributes, edge_attributes
        )

        # Create edge statement
        edge_attrs = []
        if edge_label:
            edge_attrs.append(f'label="{_escape_dot_string(edge_label)}"')

        if bidirectional:
            edge_attrs.append('dir="both"')
        else:
            edge_attrs.append('dir="forward"')

        if edge_attrs:
            lines.append(
                f'  "{_escape_dot_string(source)}" -> "{_escape_dot_string(target)}" [{",".join(edge_attrs)}];'
            )
        else:
            lines.append(
                f'  "{_escape_dot_string(source)}" -> "{_escape_dot_string(target)}";'
            )

    lines.append("}")
    result = "\n".join(lines)

    # Optionally save to file
    if output_file:
        from pathlib import Path

        Path(output_file).write_text(result, encoding="utf-8")

    return result


async def generate_graph_mermaid(
    context: GraphContext,
    graph_type: str = "graph",
    include_attributes: bool = True,
    node_filter: Optional[Callable[[Dict[str, Any]], bool]] = None,
    edge_filter: Optional[Callable[[Dict[str, Any]], bool]] = None,
    node_attributes: Optional[List[str]] = None,
    edge_attributes: Optional[List[str]] = None,
    direction: str = "TB",
    theme: Optional[str] = None,
    output_file: Optional[str] = None,
) -> str:
    """Generate a Mermaid representation of the graph.

    Args:
        context: GraphContext instance for accessing graph data
        graph_type: Type of graph: "graph" (undirected) or "flowchart" (directed)
        include_attributes: Whether to include node/edge attributes as labels
        node_filter: Optional function to filter nodes (receives node dict, returns bool)
        edge_filter: Optional function to filter edges (receives edge dict, returns bool)
        node_attributes: List of node attributes to include in label (None = all)
        edge_attributes: List of edge attributes to include in label (None = all)
        direction: Graph direction: TB, TD, BT, RL, LR
        theme: Optional theme: default, dark, forest, neutral

    Returns:
        Mermaid format string suitable for rendering in Markdown or Mermaid tools

    Keyword Args:
        output_file: Optional file path to save the Mermaid output. If provided, the graph
                    will be written to this file in addition to being returned.

    Example:
        ```python
        from jvspatial.core.context import get_default_context
        from jvspatial.core.graph import generate_graph_mermaid

        context = get_default_context()
        mermaid = await generate_graph_mermaid(
            context,
            graph_type="flowchart",
            direction="LR"
        )
        print(mermaid)
        ```
    """
    # Get all nodes and edges from database
    nodes_data = await context.database.find("node", {})
    edges_data = await context.database.find("edge", {})

    # Apply filters if provided
    if node_filter:
        nodes_data = [n for n in nodes_data if node_filter(n)]
    if edge_filter:
        edges_data = [e for e in edges_data if edge_filter(e)]

    # Build node set from edges to ensure all referenced nodes are included
    referenced_node_ids = set()
    for edge in edges_data:
        referenced_node_ids.add(edge.get("source"))
        referenced_node_ids.add(edge.get("target"))

    # Start Mermaid diagram
    lines = [f"{graph_type} {direction}"]

    # Add theme if specified
    if theme:
        lines.append(f"%%{theme}")

    # Process nodes - create a mapping of node_id to node_name for cleaner labels
    node_id_map: Dict[str, str] = {}
    for node_data in nodes_data:
        node_id = node_data.get("id", "")
        node_name = node_data.get("name", "Unknown")
        context_data = node_data.get("context", {})

        # Skip if node is not referenced
        if node_id not in referenced_node_ids and not any(
            n.get("id") == node_id for n in nodes_data
        ):
            continue

        # Build node label
        node_label = _build_node_label(
            node_name,
            node_id,
            context_data,
            include_attributes,
            node_attributes,
            format="mermaid",
        )

        # Create node identifier (simplified for Mermaid)
        node_identifier = _sanitize_mermaid_id(node_id)
        node_id_map[node_id] = node_identifier

        # Add styling for root node
        style = ""
        if node_data.get("is_root"):
            style = ":::root"

        lines.append(
            f'    {node_identifier}["{_escape_mermaid_string(node_label)}"]{style}'
        )

    # Process edges
    for edge_data in edges_data:
        source = edge_data.get("source")
        target = edge_data.get("target")
        bidirectional = edge_data.get("bidirectional", False)
        context_data = edge_data.get("context", {})

        if not source or not target:
            continue

        source_id = node_id_map.get(source, _sanitize_mermaid_id(source))
        target_id = node_id_map.get(target, _sanitize_mermaid_id(target))

        # Build edge label
        edge_label = _build_edge_label(
            context_data, include_attributes, edge_attributes
        )

        # Create edge statement
        if bidirectional:
            connector = "<-->"
        else:
            connector = "-->"

        if edge_label:
            lines.append(
                f'    {source_id} {connector}|"{_escape_mermaid_string(edge_label)}"| {target_id}'
            )
        else:
            lines.append(f"    {source_id} {connector} {target_id}")

    # Add styling for root nodes if any
    if any(n.get("is_root") for n in nodes_data):
        lines.append("    classDef root fill:#e1f5ff,stroke:#01579b,stroke-width:2px")

    result = "\n".join(lines)

    # Optionally save to file
    if output_file:
        from pathlib import Path

        Path(output_file).write_text(result, encoding="utf-8")

    return result


def _build_node_label(
    node_name: str,
    node_id: str,
    context_data: Dict[str, Any],
    include_attributes: bool,
    node_attributes: Optional[List[str]],
    format: str = "dot",
) -> str:
    """Build a label for a node."""
    if format == "mermaid":
        # For Mermaid, use a simpler format
        label_parts = [node_name]
        if include_attributes and context_data:
            attrs_to_show = (
                node_attributes or list(context_data.keys())[:3]
            )  # Limit to 3 for readability
            for attr in attrs_to_show:
                if attr in context_data and not attr.startswith("_"):
                    value = str(context_data[attr])[:30]  # Truncate long values
                    label_parts.append(f"{attr}: {value}")
        return "\\n".join(label_parts)
    else:
        # DOT format - more detailed
        label_parts = [f"{node_name}\\n({_shorten_id(node_id)})"]
        if include_attributes and context_data:
            attrs_to_show = node_attributes or list(context_data.keys())
            for attr in attrs_to_show:
                if attr in context_data and not attr.startswith("_"):
                    value = str(context_data[attr])
                    if len(value) > 40:
                        value = value[:37] + "..."
                    label_parts.append(f"{attr}: {value}")
        return "\\l".join(label_parts) + "\\l"


def _build_edge_label(
    context_data: Dict[str, Any],
    include_attributes: bool,
    edge_attributes: Optional[List[str]],
) -> str:
    """Build a label for an edge."""
    if not include_attributes or not context_data:
        return ""

    attrs_to_show = (
        edge_attributes or list(context_data.keys())[:2]
    )  # Limit for readability
    label_parts = []
    for attr in attrs_to_show:
        if attr in context_data and not attr.startswith("_"):
            value = str(context_data[attr])
            if len(value) > 20:
                value = value[:17] + "..."
            label_parts.append(f"{attr}: {value}")

    return ", ".join(label_parts)


def _escape_dot_string(s: str) -> str:
    """Escape special characters for DOT format."""
    return s.replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def _escape_mermaid_string(s: str) -> str:
    """Escape special characters for Mermaid format."""
    return s.replace('"', "&quot;").replace("\n", "<br/>")


def _sanitize_mermaid_id(node_id: str) -> str:
    """Convert node ID to a valid Mermaid identifier."""
    # Replace special characters with underscores
    sanitized = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in node_id)
    # Ensure it starts with a letter
    if sanitized and not sanitized[0].isalpha():
        sanitized = "n" + sanitized
    return sanitized[:50]  # Limit length


def _shorten_id(node_id: str, max_length: int = 20) -> str:
    """Shorten a node ID for display."""
    if len(node_id) <= max_length:
        return node_id
    # Try to extract meaningful parts
    parts = node_id.split(":")
    if len(parts) > 1:
        return ":".join(parts[-2:])  # Keep last two parts
    return node_id[: max_length - 3] + "..."


# Convenience function for GraphContext
async def export_graph(
    context: GraphContext,
    format: str = "dot",
    output_file: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Export graph in specified format.

    Args:
        context: GraphContext instance
        format: Output format: "dot" or "mermaid"
        output_file: Optional file path to save the output. If provided, the graph
                    will be written to this file in addition to being returned.
        **kwargs: Additional arguments passed to format-specific generator

    Returns:
        Graph representation string

    Example:
        ```python
        from jvspatial.core.context import get_default_context
        from jvspatial.core.graph import export_graph

        context = get_default_context()
        dot_graph = await export_graph(context, format="dot")
        mermaid_graph = await export_graph(context, format="mermaid", direction="LR")

        # Save to file optionally
        dot_graph = await export_graph(context, format="dot", output_file="graph.dot")
        ```
    """
    # Pass output_file to the format-specific generator
    if output_file:
        kwargs["output_file"] = output_file

    if format.lower() == "dot":
        return await generate_graph_dot(context, **kwargs)
    elif format.lower() == "mermaid":
        return await generate_graph_mermaid(context, **kwargs)
    else:
        raise ValueError(f"Unsupported format: {format}. Use 'dot' or 'mermaid'")
