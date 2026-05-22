"""
Rename Impact Graph — transitive impact analysis for safe refactors.

Given a symbol rename/change:
1. Find all references (via LSP or symbol graph)
2. Find all callers (direct)
3. Find transitive callers (indirect impact)
4. Calculate impact radius
5. Rank by risk

Critical for: safe auto-apply, refactor confidence, rename planning.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def build_impact_graph(
    symbol: str,
    project_root: Path,
    max_depth: int = 3,
    max_nodes: int = 100,
) -> Dict[str, Any]:
    """
    Build a transitive impact graph for a symbol.

    Returns: {symbol, direct_references, callers, transitive_impact, risk_level}
    """
    try:
        from .symbols import find_symbols
    except ImportError:
        from symbols import find_symbols

    # Step 1: Find all occurrences of the symbol
    occurrences = find_symbols(symbol, project_root, limit=100)
    matches = occurrences.get("matches", []) if isinstance(occurrences, dict) else []

    # Step 2: Find direct references (via LSP if available)
    direct_refs = _find_direct_references(symbol, project_root)

    # Step 3: Build caller graph
    callers = _find_callers(symbol, matches, project_root)

    # Step 4: Transitive closure
    transitive = _transitive_closure(symbol, callers, project_root, max_depth, max_nodes)

    # Step 5: Calculate impact
    impact = _calculate_impact(symbol, matches, direct_refs, callers, transitive)

    return {
        "symbol": symbol,
        "occurrences": len(matches),
        "direct_references": len(direct_refs),
        "direct_callers": len(callers),
        "transitive_callers": len(transitive),
        "callers": callers,
        "transitive_impact": transitive,
        "impact_radius": impact["radius"],
        "risk_level": impact["risk"],
        "affected_files": impact["files"],
        "recommendation": _recommend(impact),
    }


def _find_direct_references(symbol: str, project_root: Path) -> List[Dict]:
    """Find direct references using LSP or symbol graph."""
    refs = []
    try:
        from .lsp_bridge import find_all_references
        # Try LSP on first occurrence
        try:
            from .symbols import find_symbols
            occurrences = find_symbols(symbol, project_root, limit=1)
            matches = occurrences.get("matches", []) if isinstance(occurrences, dict) else []
            if matches:
                first = matches[0]
                lsp_refs = find_all_references(
                    first.get("file", ""),
                    first.get("line", 1),
                    1,
                    project_root,
                )
                if lsp_refs.get("available"):
                    refs = lsp_refs.get("references", [])
        except Exception:
            pass
    except Exception:
        pass

    if not refs:
        # Fallback: use symbol graph
        try:
            from .symbols import find_symbols
        except ImportError:
            from symbols import find_symbols
        occurrences = find_symbols(symbol, project_root, limit=50)
        matches = occurrences.get("matches", []) if isinstance(occurrences, dict) else []
        refs = [{"file": m.get("file"), "line": m.get("line")} for m in matches]

    return refs


def _find_callers(symbol: str, matches: List[Dict], project_root: Path) -> List[Dict]:
    """Find direct callers of a symbol."""
    callers = []
    seen = set()

    # For each file containing the symbol, look for call-like patterns
    # This is a heuristic — full caller analysis requires AST/LSP
    for match in matches[:10]:
        file_path = match.get("file", "")
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)

        full_path = project_root / file_path
        if not full_path.exists():
            continue

        try:
            text = full_path.read_text(encoding="utf-8", errors="ignore")
            symbol_clean = symbol.split("(")[0].strip()

            # Simple heuristic: find lines where the symbol appears in a call context
            for line_no, line in enumerate(text.splitlines(), start=1):
                if symbol_clean in line and (
                    "(" in line or "->" in line or "::" in line or "." in line
                ):
                    # Find the enclosing function/class
                    context = _find_enclosing_context(text, line_no)
                    if context:
                        callers.append({
                            "symbol": context.get("name", f"line:{line_no}"),
                            "type": context.get("type", "function"),
                            "file": file_path,
                            "line": line_no,
                        })
                        if len(callers) >= 50:
                            break
        except OSError:
            pass

    return callers[:50]


def _find_enclosing_context(text: str, line_no: int) -> Optional[Dict]:
    """Find the enclosing function/class for a given line."""
    import re
    lines = text.splitlines()
    context = None

    for i in range(line_no - 1, -1, -1):
        line = lines[i].strip()
        # Class
        m = re.search(r'class\s+([A-Za-z_][A-Za-z0-9_]*)', line)
        if m:
            context = {"name": m.group(1), "type": "class"}
            break
        # Function
        m = re.search(r'(?:def|function)\s+([A-Za-z_][A-Za-z0-9_]*)', line)
        if m:
            context = {"name": m.group(1), "type": "function"}
            break

    return context


def _transitive_closure(
    symbol: str,
    callers: List[Dict],
    project_root: Path,
    max_depth: int,
    max_nodes: int,
) -> List[Dict]:
    """Compute transitive callers using BFS."""
    visited: Set[str] = set()
    transitive = []
    queue = deque()

    for caller in callers[:10]:
        key = f"{caller.get('file')}:{caller.get('symbol')}"
        if key not in visited:
            visited.add(key)
            queue.append((caller, 1))  # (caller, depth)

    while queue and len(transitive) < max_nodes:
        caller, depth = queue.popleft()
        transitive.append({**caller, "depth": depth})

        if depth >= max_depth:
            continue

        # Find callers of this caller
        caller_symbol = caller.get("symbol", "")
        if caller_symbol and caller_symbol != symbol:
            sub_callers = _find_callers(caller_symbol, [caller], project_root)
            for sub in sub_callers[:5]:
                key = f"{sub.get('file')}:{sub.get('symbol')}"
                if key not in visited:
                    visited.add(key)
                    queue.append((sub, depth + 1))

    return transitive


def _calculate_impact(
    symbol: str,
    matches: List[Dict],
    refs: List[Dict],
    callers: List[Dict],
    transitive: List[Dict],
) -> Dict[str, Any]:
    """Calculate impact radius and risk level."""
    all_files = set()
    all_files.update(m.get("file") for m in matches if m.get("file"))
    all_files.update(r.get("file") for r in refs if r.get("file"))
    all_files.update(c.get("file") for c in callers if c.get("file"))
    all_files.update(t.get("file") for t in transitive if t.get("file"))
    all_files.discard(None)

    file_count = len(all_files)
    depth = max((t.get("depth", 1) for t in transitive), default=1)

    if file_count <= 2:
        radius, risk = "local", "low"
    elif file_count <= 5:
        radius, risk = "module", "low"
    elif file_count <= 15 and depth <= 2:
        radius, risk = "cross_module", "medium"
    elif file_count <= 30:
        radius, risk = "repository", "high"
    else:
        radius, risk = "system_wide", "critical"

    return {
        "radius": radius,
        "risk": risk,
        "files": sorted(all_files)[:30],
        "file_count": file_count,
        "max_depth": depth,
    }


def _recommend(impact: Dict[str, Any]) -> str:
    """Generate recommendation based on impact analysis."""
    risk = impact.get("risk", "low")
    files = impact.get("file_count", 0)

    if risk == "critical":
        return f"CRITICAL: {files} files affected. Manual review required. Run full test suite."
    if risk == "high":
        return f"HIGH: {files} files affected. Review callers carefully. Run related tests."
    if risk == "medium":
        return f"MEDIUM: {files} files affected. Check callers. Run module tests."
    return f"LOW: Safe to proceed. {files} files affected."


# ── Semantic Operation Taxonomy ──────────────────────────────────

def classify_operation(changes: List[Dict]) -> str:
    """
    Classify a set of changes into a semantic operation type.
    Used by structural diff + confidence engine.
    """
    types = {c.get("type", "") for c in changes}
    actions = {c.get("action", "") for c in changes}

    if "sql_change" in types:
        return "SCHEMA_MUTATION"
    if "class_definition" in types and "added" in actions:
        return "ADD_CLASS"
    if "class_definition" in types and "removed" in actions:
        return "REMOVE_CLASS"
    if "function_signature" in types and "added" in actions and "removed" in actions:
        return "CHANGE_SIGNATURE"
    if "function_signature" in types and "added" in actions:
        return "ADD_METHOD"
    if "function_signature" in types and "removed" in actions:
        return "REMOVE_METHOD"
    if "import" in types and "added" in actions:
        return "ADD_DEPENDENCY"
    if "import" in types and "removed" in actions:
        return "REMOVE_DEPENDENCY"
    if "property" in types and "added" in actions:
        return "ADD_FIELD"
    if "property" in types and "removed" in actions:
        return "REMOVE_FIELD"
    if "annotation" in types:
        return "CHANGE_ANNOTATION"
    if "return_type" in types:
        return "CHANGE_RETURN_TYPE"

    return "MODIFY_IMPLEMENTATION"


# ── Daemon handlers ──────────────────────────────────────────────

def handle_impact_graph(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build rename impact graph."""
    symbol = params.get("symbol", "")
    project_root = Path(params.get("project_root", "."))
    max_depth = params.get("max_depth", 3)
    return build_impact_graph(symbol, project_root, max_depth)


def handle_classify_operation(params: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a set of changes into a semantic operation type."""
    changes = params.get("changes", [])
    op_type = classify_operation(changes)
    return {"operation_type": op_type, "change_count": len(changes)}
