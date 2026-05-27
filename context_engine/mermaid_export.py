"""
Mermaid Export — visualize primitive dependency graph and execution DAG.

Generates Mermaid diagrams for:
  - Primitive dependency graph (who depends on whom)
  - Execution DAG stages (which primitives run in parallel)
  - Category overview (which categories have which primitives)
"""
from __future__ import annotations

from typing import Dict, List

from .primitives import get_registry, build_execution_dag, Primitive


def primitive_dependency_diagram() -> str:
    """Generate Mermaid diagram of all primitive dependencies."""
    reg = get_registry()
    lines = ["graph TD"]

    # Color by category
    category_colors = {
        "graph": "#4a9eff",
        "verify": "#ff6b6b",
        "memory": "#ffd93d",
        "git": "#6bff6b",
        "risk": "#ff9f43",
        "test": "#a29bfe",
        "context": "#00d2d3",
        "lint": "#feca57",
    }

    # Define nodes
    for name, prim in reg.items():
        cat = prim.contract.category if hasattr(prim.contract, 'category') else prim.category
        color = category_colors.get(cat, "#999")
        safe_name = name.replace(".", "_").replace("-", "_")
        lines.append(f'    {safe_name}["{name}"]')
        # Style with category color
        lines.append(f'    style {safe_name} fill:{color}')

    # Define edges (dependencies)
    for name, prim in reg.items():
        safe_name = name.replace(".", "_").replace("-", "_")
        for dep in prim.contract.depends_on:
            safe_dep = dep.replace(".", "_").replace("-", "_")
            lines.append(f"    {safe_dep} --> {safe_name}")

    return "\n".join(lines)


def execution_stages_diagram(primitive_names: List[str]) -> str:
    """Generate Mermaid diagram showing execution stages in DAG order."""
    stages = build_execution_dag(primitive_names)

    lines = ["graph TD"]
    lines.append("    subgraph \"Execution DAG Stages\"")

    for stage_idx, stage in enumerate(stages):
        stage_name = f"Stage {stage_idx + 1}"
        lines.append(f"    subgraph \"{stage_name}\"")
        for prim_name in stage:
            safe = prim_name.replace(".", "_").replace("-", "_")
            lines.append(f"        {safe}_{stage_idx}[\"{prim_name}\"]")
        lines.append("    end")

    # Add arrows between stages
    for stage_idx in range(len(stages) - 1):
        for prim_name in stages[stage_idx]:
            safe_from = prim_name.replace(".", "_").replace("-", "_")
            for next_name in stages[stage_idx + 1]:
                safe_to = next_name.replace(".", "_").replace("-", "_")
                lines.append(f"    {safe_from}_{stage_idx} --> {safe_to}_{stage_idx + 1}")

    lines.append("    end")
    return "\n".join(lines)


def category_overview_diagram() -> str:
    """Generate Mermaid mindmap showing primitive categories and their contents."""
    reg = get_registry()

    categories: Dict[str, List[str]] = {}
    for name, prim in reg.items():
        cat = prim.contract.category if hasattr(prim.contract, 'category') else prim.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(name)

    lines = ["graph LR"]
    for cat, names in sorted(categories.items()):
        safe_cat = cat.replace(".", "_")
        lines.append(f'    {safe_cat}["{cat} ({len(names)})"]')
        for name in names:
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f"    {safe_cat} --- {safe_name}[\"{name.split('.')[-1]}\"]")

    return "\n".join(lines)


def export_all_diagrams() -> Dict[str, str]:
    """Export all available Mermaid diagrams."""
    return {
        "dependency_graph": primitive_dependency_diagram(),
        "category_overview": category_overview_diagram(),
    }


def handle_mermaid_export(params: Dict[str, Any]) -> Dict[str, Any]:
    """Export primitive graph as Mermaid."""
    diagram_type = str(params.get("type", "dependency"))
    primitives_list = params.get("primitives", []) if isinstance(params.get("primitives"), list) else []

    if diagram_type == "stages" and primitives_list:
        mermaid = execution_stages_diagram(primitives_list)
    elif diagram_type == "category":
        mermaid = category_overview_diagram()
    else:
        mermaid = primitive_dependency_diagram()

    return {
        "diagram_type": diagram_type,
        "mermaid": mermaid,
        "primitive_count": len(get_registry()),
    }
