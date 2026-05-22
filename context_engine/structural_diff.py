"""
Structural Diff — AST-aware patch analysis.

Goes beyond textual diff to detect:
- Renamed methods/functions
- Changed signatures (params added/removed)
- Changed return types
- Added/removed imports
- Changed SQL queries
- Changed annotations/decorators
- Structural impact radius

Feeds into confidence scoring for smarter auto-apply decisions.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def analyze_patch(patch_text: str) -> Dict[str, Any]:
    """Analyze a unified diff patch for structural changes."""
    changes = _parse_diff_changes(patch_text)
    
    return {
        "files_changed": len(set(c["file"] for c in changes)),
        "changes": changes,
        "structural_summary": _summarize_changes(changes),
        "impact_radius": _calculate_impact_radius(changes),
        "risk_level": _assess_risk(changes),
    }


def _parse_diff_changes(patch_text: str) -> List[Dict[str, Any]]:
    """Parse unified diff into structured changes."""
    changes = []
    current_file = None
    current_hunk = None
    
    for line in patch_text.splitlines():
        # File header
        if line.startswith("--- ") or line.startswith("+++ "):
            parts = line[4:].strip().split("\t")[0]
            if parts != "/dev/null":
                current_file = parts.lstrip("ab/")
            continue
        
        # Hunk header
        if line.startswith("@@"):
            current_hunk = line
            continue
        
        if not current_file:
            continue
        
        # Added line
        if line.startswith("+") and not line.startswith("+++"):
            change = _classify_line(line[1:], "added", current_file)
            if change:
                changes.append(change)
        
        # Removed line
        elif line.startswith("-") and not line.startswith("---"):
            change = _classify_line(line[1:], "removed", current_file)
            if change:
                changes.append(change)
    
    return changes


def _classify_line(line: str, action: str, file_path: str) -> Optional[Dict[str, Any]]:
    """Classify a single changed line."""
    stripped = line.strip()
    
    # Function/method definition
    func_match = re.search(
        r'(?:def|function|public\s+function|private\s+function|protected\s+function'
        r'|static\s+function|export\s+function|async\s+function)\s+([A-Za-z_][A-Za-z0-9_]*)',
        stripped
    )
    if func_match:
        params = _extract_params(stripped)
        return {
            "type": "function_signature",
            "name": func_match.group(1),
            "action": action,
            "file": file_path,
            "params": params,
            "line": stripped[:200],
        }
    
    # Class/interface definition
    class_match = re.search(
        r'(?:class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)',
        stripped
    )
    if class_match:
        return {
            "type": "class_definition",
            "name": class_match.group(1),
            "action": action,
            "file": file_path,
            "line": stripped[:200],
        }
    
    # Import change
    import_match = re.search(
        r'(?:import|from|require|use)\s+',
        stripped
    )
    if import_match:
        return {
            "type": "import",
            "action": action,
            "file": file_path,
            "line": stripped[:200],
        }
    
    # SQL query (CREATE, ALTER, DROP, INSERT, UPDATE, DELETE)
    sql_match = re.search(
        r'(?:CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|SELECT)\s+',
        stripped, re.IGNORECASE
    )
    if sql_match:
        return {
            "type": "sql_change",
            "action": action,
            "file": file_path,
            "line": stripped[:200],
        }
    
    # Annotation/decorator
    if stripped.startswith("@") or stripped.startswith("#[") or stripped.startswith("/*@"):
        return {
            "type": "annotation",
            "action": action,
            "file": file_path,
            "line": stripped[:200],
        }
    
    # Return type hint change
    if "->" in stripped and action == "added":
        return {
            "type": "return_type",
            "action": action,
            "file": file_path,
            "line": stripped[:200],
        }
    
    # Property/field
    prop_match = re.search(
        r'(?:public|private|protected|var|let|const)\s+\$?([A-Za-z_][A-Za-z0-9_]*)',
        stripped
    )
    if prop_match:
        return {
            "type": "property",
            "name": prop_match.group(1),
            "action": action,
            "file": file_path,
            "line": stripped[:200],
        }
    
    return None


def _extract_params(line: str) -> List[str]:
    """Extract parameter names from a function signature."""
    match = re.search(r'\(([^)]*)\)', line)
    if not match:
        return []
    params_str = match.group(1)
    if not params_str.strip():
        return []
    params = []
    for param in params_str.split(","):
        param = param.strip()
        # Extract just the variable name from type-hinted params
        name_match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*$', param)
        if name_match and name_match.group(1) not in ("int", "str", "bool", "void", "None"):
            params.append(name_match.group(1))
        elif param:
            params.append(param.split()[-1] if param.split() else param)
    return params


def _summarize_changes(changes: List[Dict]) -> Dict[str, Any]:
    """Create a structural summary of all changes."""
    by_type = {}
    for c in changes:
        t = c.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    
    # Detect renames (same name, different files or added+removed)
    added_names = {c["name"] for c in changes if c.get("name") and c["action"] == "added"}
    removed_names = {c["name"] for c in changes if c.get("name") and c["action"] == "removed"}
    potential_renames = added_names & removed_names
    
    # Detect signature changes (same function, different params)
    signature_changes = []
    func_changes = [c for c in changes if c.get("type") == "function_signature"]
    by_func: Dict[str, List[Dict]] = {}
    for c in func_changes:
        by_func.setdefault(c["name"], []).append(c)
    for name, entries in by_func.items():
        if len(entries) >= 2:
            params_sets = {tuple(e.get("params", [])) for e in entries}
            if len(params_sets) > 1:
                signature_changes.append({
                    "function": name,
                    "variants": [list(p) for p in params_sets],
                })
    
    return {
        "by_type": by_type,
        "total_changes": len(changes),
        "potential_renames": list(potential_renames),
        "signature_changes": signature_changes,
        "has_sql_changes": by_type.get("sql_change", 0) > 0,
        "has_import_changes": by_type.get("import", 0) > 0,
    }


def _calculate_impact_radius(changes: List[Dict]) -> Dict[str, Any]:
    """Calculate how far the changes ripple."""
    files = list({c["file"] for c in changes})
    func_changes = [c for c in changes if c.get("type") == "function_signature"]
    class_changes = [c for c in changes if c.get("type") == "class_definition"]
    
    radius = "local"
    score = 0
    
    if class_changes:
        radius = "module"
        score += 3
    if any(c["type"] in ("import", "sql_change") for c in changes):
        radius = "cross_module"
        score += 5
    if len(files) > 5:
        radius = "repository"
        score += 7
    
    return {
        "radius": radius,
        "score": score,
        "affected_files": len(files),
        "affected_functions": len(func_changes),
        "affected_classes": len(class_changes),
    }


def _assess_risk(changes: List[Dict]) -> Dict[str, Any]:
    """Assess overall risk level of the patch."""
    summary = _summarize_changes(changes)
    impact = _calculate_impact_radius(changes)
    
    risk_factors = []
    risk_score = 0
    
    if summary.get("has_sql_changes"):
        risk_factors.append("schema_mutation")
        risk_score += 20
    
    if summary.get("signature_changes"):
        risk_factors.append("api_breaking")
        risk_score += 15
    
    if summary.get("has_import_changes"):
        risk_factors.append("dependency_shift")
        risk_score += 8
    
    if impact["score"] >= 7:
        risk_factors.append("wide_impact")
        risk_score += 10
    
    if potential_renames := summary.get("potential_renames", []):
        if len(potential_renames) > 2:
            risk_factors.append("mass_rename")
            risk_score += 5
    
    level = "low"
    if risk_score >= 20:
        level = "critical"
    elif risk_score >= 12:
        level = "high"
    elif risk_score >= 5:
        level = "medium"
    
    return {"level": level, "score": risk_score, "factors": risk_factors}


# ── Hierarchical Context Builder ─────────────────────────────────

def build_hierarchical_context(
    project_root: Path,
    focus_file: Optional[str] = None,
    focus_symbol: Optional[str] = None,
    expansion_level: int = 1,  # 1=module, 2=package, 3=repo
) -> Dict[str, Any]:
    """
    Build progressive hierarchical context.
    
    Level 1 (Module): Only the immediate module of focus
    Level 2 (Package): Module + its package
    Level 3 (Repo): Full repository view
    
    Agent expands only when confidence is low.
    """
    try:
        from .cache import load_cached_context
        from .symbols import find_symbols, symbol_context
    except ImportError:
        from cache import load_cached_context
        from symbols import find_symbols, symbol_context
    
    ctx = {"level": expansion_level, "layers": {}}
    
    # Level 1: Module scope
    if focus_file:
        module = Path(focus_file).parent.name
        symbols = []
        try:
            result = find_symbols("", project_root, limit=50)
            if isinstance(result, dict):
                module_symbols = [
                    s for s in result.get("matches", [])
                    if s.get("file", "").startswith(str(Path(focus_file).parent))
                ]
                symbols = module_symbols[:20]
        except Exception:
            pass
        ctx["layers"]["module"] = {
            "name": module,
            "file_count": 1,
            "symbols": [s.get("name") for s in symbols],
        }
    
    # Level 2: Package scope (if requested)
    if expansion_level >= 2 and focus_file:
        pkg = Path(focus_file).parent.parent.name if len(Path(focus_file).parents) > 2 else "root"
        ctx["layers"]["package"] = {
            "name": pkg,
            "parent_of": ctx["layers"].get("module", {}).get("name"),
        }
    
    # Level 3: Repo scope (if requested)
    if expansion_level >= 3:
        try:
            repo = load_cached_context(project_root)
            ctx["layers"]["repo"] = {
                "file_count": repo.get("repo_summary", {}).get("file_count", 0),
                "extension_counts": repo.get("repo_summary", {}).get("extension_counts", {}),
            }
        except Exception:
            pass
    
    # Focus symbol context (always include if provided)
    if focus_symbol:
        try:
            sym_ctx = symbol_context(focus_symbol, project_root, limit=10)
            ctx["focus_symbol"] = sym_ctx
        except Exception:
            pass
    
    return ctx


# ── Daemon handlers ──────────────────────────────────────────────

def handle_structural_diff(params: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze a patch structurally."""
    patch_text = params.get("patch_text", "")
    if not patch_text:
        return {"error": "no patch_text provided"}
    return analyze_patch(patch_text)


def handle_hierarchical_context(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build hierarchical context with progressive expansion."""
    project_root = Path(params.get("project_root", "."))
    focus_file = params.get("focus_file")
    focus_symbol = params.get("focus_symbol")
    expansion_level = params.get("expansion_level", 1)
    return build_hierarchical_context(project_root, focus_file, focus_symbol, expansion_level)
