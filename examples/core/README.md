# Core Examples

## Graph Visualization Example

**File:** `graph_visualization_example.py`

Demonstrates how to generate renderable graph representations using the `graph` module.
Creates a realistic graph of interconnected nodes (Organizations, People, Projects, Skills)
and exports it in multiple formats:

- **DOT/Graphviz format** - For rendering with Graphviz tools
- **Mermaid format** - For rendering in Markdown, GitHub, or Mermaid tools

The example showcases:
- Creating diverse node types with attributes
- Connecting nodes with bidirectional and unidirectional edges
- Generating visualizations with different layouts and styles
- Filtering graphs to show specific node types
- Using both direct function calls and the convenience `export_graph()` function

**Usage:**
```bash
python examples/core/graph_visualization_example.py
```

Outputs 8 files (4 DOT + 4 Mermaid variations) that can be rendered with appropriate tools.

---

This directory contains examples demonstrating core jvspatial features and graph operations.

## Example Files

### cities.py
Demonstrates graph modeling using cities and their connections:
- Node and edge creation
- Spatial relationships
- Distance calculations
- Path finding
- Node properties and metadata

### spatial_search.py
Implements spatial search functionality:
- Geospatial queries
- Distance-based filtering
- Area/region searches
- Coordinate system handling
- Spatial index usage

### context/graphcontext_demo.py
Shows how to use GraphContext for isolated operations:
- Context creation and management
- Transaction handling
- Isolated graph operations
- Error handling and rollback

### context/simple_dynamic_example.py
Demonstrates dynamic graph manipulation:
- Runtime node creation
- Dynamic relationship building
- Graph structure modification
- State management

### models/agent_graph.py
Implements a hierarchical agent system:
- Agent hierarchy modeling
- Inter-agent relationships
- State propagation
- Event handling

### models/travel_graph.py
Builds a travel planning system:
- Route optimization
- Connection management
- Travel time calculation
- Cost optimization

## Key Concepts

1. **Node Management**
   - Creation and deletion
   - Property management
   - Relationship handling

2. **Graph Operations**
   - Traversal patterns
   - Path finding
   - Subgraph isolation
   - Query optimization

3. **Spatial Features**
   - Coordinate handling
   - Distance calculations
   - Area searches
   - Spatial indexing

4. **Context Handling**
   - GraphContext usage
   - Transaction management
   - Error handling
   - State isolation

## Running Examples

```bash
# Basic city graph example
python cities.py

# Spatial search features
python spatial_search.py

# GraphContext demonstration
python context/graphcontext_demo.py
```

## Best Practices

1. Always use appropriate node types for your data
2. Implement proper error handling
3. Use GraphContext for isolated operations
4. Optimize queries for performance
5. Document node and relationship schemas
6. Use meaningful property names
7. Consider indexing for frequent queries
