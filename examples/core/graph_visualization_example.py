"""Graph Visualization Example

This example demonstrates how to create a graph of interconnected nodes
and export it in multiple formats (DOT/Graphviz and Mermaid) using the
graph visualization utilities.

The example:
1. Creates a graph structure with various node types
2. Connects nodes with different edge types (bidirectional and unidirectional)
3. Exports the graph in DOT format (Graphviz)
4. Exports the graph in Mermaid format
5. Saves outputs to files for rendering

Usage:
    python graph_visualization_example.py

The output files will be created in the current directory:
    - graph_output.dot (Graphviz format)
    - graph_output.mermaid (Mermaid format)
"""

import asyncio
from pathlib import Path

from jvspatial.core import GraphContext, Node
from jvspatial.core.context import set_default_context
from jvspatial.core.graph import (
    export_graph,
    generate_graph_dot,
    generate_graph_mermaid,
)
from jvspatial.db.factory import create_database

# =============================================================================
# DEFINE NODE CLASSES
# =============================================================================


class PersonNode(Node):
    """Person node in the graph."""

    name: str = ""
    age: int = 0
    role: str = ""
    email: str = ""


class OrganizationNode(Node):
    """Organization node in the graph."""

    name: str = ""
    industry: str = ""
    location: str = ""
    founded: int = 0


class ProjectNode(Node):
    """Project node in the graph."""

    title: str = ""
    status: str = ""
    budget: float = 0.0
    start_date: str = ""


class SkillNode(Node):
    """Skill node in the graph."""

    name: str = ""
    category: str = ""
    proficiency: str = ""


# =============================================================================
# BUILD THE GRAPH
# =============================================================================


async def build_graph(context: GraphContext):
    """Build a realistic graph structure."""

    print("Building graph structure...")

    # Create organizations
    acme_corp = await OrganizationNode.create(
        name="Acme Corporation",
        industry="Technology",
        location="San Francisco, CA",
        founded=2010,
    )

    tech_startup = await OrganizationNode.create(
        name="TechStart Inc", industry="Software", location="Austin, TX", founded=2018
    )

    # Create people
    alice = await PersonNode.create(
        name="Alice Johnson",
        age=32,
        role="Software Engineer",
        email="alice@example.com",
    )

    bob = await PersonNode.create(
        name="Bob Smith", age=28, role="Data Scientist", email="bob@example.com"
    )

    carol = await PersonNode.create(
        name="Carol Davis", age=35, role="Project Manager", email="carol@example.com"
    )

    dave = await PersonNode.create(
        name="Dave Wilson", age=30, role="DevOps Engineer", email="dave@example.com"
    )

    # Create projects
    project_alpha = await ProjectNode.create(
        title="Project Alpha", status="Active", budget=500000.0, start_date="2024-01-15"
    )

    project_beta = await ProjectNode.create(
        title="Project Beta",
        status="Planning",
        budget=300000.0,
        start_date="2024-03-01",
    )

    # Create skills
    python_skill = await SkillNode.create(
        name="Python", category="Programming", proficiency="Expert"
    )

    ml_skill = await SkillNode.create(
        name="Machine Learning", category="Data Science", proficiency="Advanced"
    )

    devops_skill = await SkillNode.create(
        name="DevOps", category="Infrastructure", proficiency="Expert"
    )

    print(
        f"  ✓ Created {len([acme_corp, tech_startup, alice, bob, carol, dave, project_alpha, project_beta, python_skill, ml_skill, devops_skill])} nodes"
    )

    # Connect nodes with edges
    # People to Organizations (bidirectional - they work for)
    # Note: connect() defaults to direction="out" for forward connections
    await alice.connect(acme_corp)
    await bob.connect(acme_corp)
    await carol.connect(tech_startup)
    await dave.connect(tech_startup)

    # People to Projects (unidirectional - they work on)
    await alice.connect(project_alpha)
    await bob.connect(project_alpha)
    await carol.connect(project_beta)
    await dave.connect(project_beta)

    # People to Skills (bidirectional - they have)
    await alice.connect(python_skill)
    await bob.connect(ml_skill)
    await dave.connect(devops_skill)
    await bob.connect(python_skill)  # Bob also knows Python

    # Projects to Organizations (unidirectional - projects belong to)
    await project_alpha.connect(acme_corp)
    await project_beta.connect(tech_startup)

    # People connections (bidirectional - they collaborate)
    await alice.connect(bob)
    await carol.connect(dave)

    print(f"  ✓ Created interconnections between nodes")

    return {
        "organizations": [acme_corp, tech_startup],
        "people": [alice, bob, carol, dave],
        "projects": [project_alpha, project_beta],
        "skills": [python_skill, ml_skill, devops_skill],
    }


# =============================================================================
# VISUALIZE THE GRAPH
# =============================================================================


async def visualize_graph(context: GraphContext):
    """Generate graph visualizations in all available formats."""

    print("\nGenerating graph visualizations...")

    # Get root node for reference
    from jvspatial.core.entities import Root

    root = await Root.get(None)  # type: ignore[assignment]

    # Connect at least one node to root for completeness
    organizations = await OrganizationNode.find()
    if organizations:
        await root.connect(organizations[0])

    # =====================================================================
    # DOT Format (Graphviz)
    # =====================================================================

    print("\n1. Generating DOT format (Graphviz)...")

    # Basic DOT export (returns value, optionally saves to file)
    dot_basic = await generate_graph_dot(
        context,
        graph_name="company_graph",
        rankdir="LR",  # Left to Right layout
        node_shape="box",
        include_attributes=True,
        output_file="graph_output_basic.dot",  # Save to file
    )

    # DOT with custom styling
    dot_styled = await generate_graph_dot(
        context,
        graph_name="company_graph_styled",
        rankdir="TB",  # Top to Bottom layout
        node_shape="ellipse",
        include_attributes=True,
        node_attributes=["name", "role", "status"],  # Limit attributes shown
        style_options={"splines": "ortho", "nodesep": "1.0", "ranksep": "1.5"},
        output_file="graph_output_styled.dot",  # Save to file
    )

    # DOT filtered view (only business-related nodes, excluding City from other examples)
    def business_node_filter(node_data: dict) -> bool:
        """Filter to show only business-related nodes (Person, Skill, Organization, Project)."""
        node_name = node_data.get("name", "")
        return node_name in [
            "PersonNode",
            "SkillNode",
            "OrganizationNode",
            "ProjectNode",
        ]

    dot_filtered = await generate_graph_dot(
        context,
        graph_name="business_graph",
        rankdir="LR",
        node_shape="circle",
        include_attributes=True,
        node_filter=business_node_filter,
        output_file="graph_output_filtered.dot",  # Save to file
    )

    print("   ✓ Generated 3 DOT variations")

    # =====================================================================
    # Mermaid Format
    # =====================================================================

    print("\n2. Generating Mermaid format...")

    # Basic Mermaid flowchart
    mermaid_flowchart = await generate_graph_mermaid(
        context,
        graph_type="flowchart",
        direction="LR",
        include_attributes=True,
        output_file="graph_output_flowchart.mermaid",  # Save to file
    )

    # Mermaid graph (undirected)
    mermaid_graph = await generate_graph_mermaid(
        context,
        graph_type="graph",
        direction="TB",
        include_attributes=True,
        node_attributes=["name"],  # Simplified view
        theme="default",
        output_file="graph_output_graph.mermaid",  # Save to file
    )

    # Mermaid with filtering
    mermaid_filtered = await generate_graph_mermaid(
        context,
        graph_type="flowchart",
        direction="LR",
        include_attributes=True,
        node_filter=business_node_filter,
        node_attributes=["name", "role", "proficiency"],
        output_file="graph_output_filtered.mermaid",  # Save to file
    )

    print("   ✓ Generated 3 Mermaid variations")

    # =====================================================================
    # Using export_graph convenience function
    # =====================================================================

    print("\n3. Using export_graph convenience function...")

    dot_convenience = await export_graph(
        context,
        format="dot",
        rankdir="LR",
        node_shape="box",
        output_file="graph_output_convenience.dot",  # Save to file
    )

    mermaid_convenience = await export_graph(
        context,
        format="mermaid",
        graph_type="flowchart",
        direction="LR",
        output_file="graph_output_convenience.mermaid",  # Save to file
    )

    print("   ✓ Generated via convenience function")

    print("\n✓ Saved graph visualizations:")
    print("   DOT files:")
    print("     - graph_output_basic.dot")
    print("     - graph_output_styled.dot")
    print("     - graph_output_filtered.dot")
    print("     - graph_output_convenience.dot")
    print("   Mermaid files:")
    print("     - graph_output_flowchart.mermaid")
    print("     - graph_output_graph.mermaid")
    print("     - graph_output_filtered.mermaid")
    print("     - graph_output_convenience.mermaid")

    # Display a sample
    print("\n" + "=" * 70)
    print("SAMPLE DOT OUTPUT (first 20 lines):")
    print("=" * 70)
    print("\n".join(dot_basic.split("\n")[:20]))
    print("...")

    print("\n" + "=" * 70)
    print("SAMPLE MERMAID OUTPUT (first 20 lines):")
    print("=" * 70)
    print("\n".join(mermaid_flowchart.split("\n")[:20]))
    print("...")


# =============================================================================
# MAIN EXECUTION
# =============================================================================


async def main():
    """Main execution function."""

    print("=" * 70)
    print("Graph Visualization Example")
    print("=" * 70)
    print()

    # Setup database and context
    db = create_database(
        db_type="json",
        base_path="./jvdb",
        auto_create=True,
    )

    context = GraphContext(database=db)
    set_default_context(context)

    print("Database and context initialized")
    print()

    # Build the graph
    graph_data = await build_graph(context)

    # Visualize the graph
    await visualize_graph(context)

    print("\n" + "=" * 70)
    print("Example completed successfully!")
    print("=" * 70)
    print("\nTo render the DOT files, use Graphviz:")
    print("  dot -Tpng graph_output_basic.dot -o graph_output_basic.png")
    print("  dot -Tsvg graph_output_styled.dot -o graph_output_styled.svg")
    print("\nTo render Mermaid files, use:")
    print("  - Mermaid Live Editor: https://mermaid.live")
    print("  - GitHub/GitLab markdown (they render Mermaid automatically)")
    print("  - VS Code with Mermaid extension")
    print()


if __name__ == "__main__":
    asyncio.run(main())
