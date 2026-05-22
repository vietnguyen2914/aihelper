from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    from .cache import build_cache, cache_paths, cache_status
    from .common import normalize_identifier, safe_load_json
except ImportError:
    from cache import build_cache, cache_paths, cache_status
    from common import normalize_identifier, safe_load_json


def _ensure_cache(project_root: Path) -> None:
    status = cache_status(project_root)
    if not status.get("fresh"):
        build_cache(project_root)


def find_symbols(query: str, project_root: Path, limit: int = 20) -> Dict[str, Any]:
    project_root = project_root.resolve()
    _ensure_cache(project_root)
    graph = safe_load_json(cache_paths(project_root)["symbol_graph"], default={}) or {}
    normalized_query = normalize_identifier(query)
    symbols = graph.get("symbols", [])
    matches: List[Dict[str, Any]] = []
    for symbol in symbols:
        name = str(symbol.get("name", ""))
        normalized = str(symbol.get("normalized", ""))
        if normalized_query == normalized or normalized_query in normalized or query.lower() in name.lower():
            matches.append(symbol)
            if len(matches) >= limit:
                break
    return {"query": query, "matches": matches, "count": len(matches), "project_root": str(project_root)}


def symbol_context(query: str, project_root: Path, limit: int = 10) -> Dict[str, Any]:
    result = find_symbols(query, project_root, limit=limit)
    paths = cache_paths(project_root.resolve())
    graph = safe_load_json(paths["symbol_graph"], default={}) or {}
    dependency_graph = safe_load_json(paths["dependency_graph"], default={}) or {}
    files = {item.get("file") for item in result.get("matches", []) if item.get("file")}
    imports_by_file = graph.get("imports_by_file", {})
    related_imports = {file_path: imports_by_file.get(file_path, [])[:20] for file_path in files}
    related_edges = [
        edge for edge in dependency_graph.get("edges", [])
        if edge.get("from") in files or edge.get("to") in files
    ][:50]
    return {
        **result,
        "files": sorted(files),
        "imports": related_imports,
        "dependency_edges": related_edges,
    }


def dependency_context(query: str, project_root: Path, limit: int = 50) -> Dict[str, Any]:
    project_root = project_root.resolve()
    _ensure_cache(project_root)
    paths = cache_paths(project_root)
    dependency_graph = safe_load_json(paths["dependency_graph"], default={}) or {}
    symbol_result = find_symbols(query, project_root, limit=10)
    files = {item.get("file") for item in symbol_result.get("matches", []) if item.get("file")}
    if not files and (project_root / query).exists():
        files.add(query)
    edges = [
        edge for edge in dependency_graph.get("edges", [])
        if not files or edge.get("from") in files or edge.get("to") in files or query in str(edge.get("to", ""))
    ][:limit]
    return {"query": query, "files": sorted(files), "edges": edges, "count": len(edges), "project_root": str(project_root)}
