"""
graph_query.py — MCP tool handlers for graph queries (v0.0.7).

Handles: callers, callees, trace, impact, explore, graph_status.
Uses SQLite graph_db for all queries, with fallback to regex-based symbol lookup.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def _find_symbol_id(name: str, root: Path) -> str | None:
    """Resolve a symbol name to its graph ID."""
    from .graph_db import get_db
    db = get_db(root)

    # Try FTS5 search
    results = db.search_symbols(name, limit=1)
    if results:
        return results[0]["id"]

    # Try exact name match
    results = db.search_by_name(name, limit=1)
    if results:
        return results[0]["id"]

    # Fallback: regex-based symbol lookup
    try:
        from .symbols import find_symbols
        matches = find_symbols(name, root, limit=1)
        if matches.get("matches"):
            m = matches["matches"][0]
            return f"{m['file']}::{m['name']}"
    except Exception:
        pass

    return None


def _format_nodes(nodes: List[Dict[str, Any]], title: str = "") -> Dict[str, Any]:
    """Format graph nodes into a compact response."""
    return {
        "title": title,
        "count": len(nodes),
        "results": [
            {
                "name": n.get("name", ""),
                "kind": n.get("kind", ""),
                "file": n.get("file_path", ""),
                "line": n.get("start_line", n.get("line", 0)),
                "depth": n.get("depth", 1),
                "signature": n.get("signature", ""),
            }
            for n in nodes
        ],
    }


# ── Handlers ──────────────────────────────────────────────────────

def handle_callers(arguments: Dict[str, Any], root: Path) -> Dict[str, Any]:
    symbol = str(arguments.get("symbol", "")).strip()
    if not symbol:
        return {"error": "symbol is required"}

    depth = int(arguments.get("depth") or 1)
    sym_id = _find_symbol_id(symbol, root)
    if not sym_id:
        return {"error": f"Symbol '{symbol}' not found in codebase"}

    from .graph_db import get_db
    db = get_db(root)
    callers = db.get_callers(sym_id, max_depth=depth)
    return _format_nodes(callers, f"Callers of {symbol}")


def handle_callees(arguments: Dict[str, Any], root: Path) -> Dict[str, Any]:
    symbol = str(arguments.get("symbol", "")).strip()
    if not symbol:
        return {"error": "symbol is required"}

    depth = int(arguments.get("depth") or 1)
    sym_id = _find_symbol_id(symbol, root)
    if not sym_id:
        return {"error": f"Symbol '{symbol}' not found in codebase"}

    from .graph_db import get_db
    db = get_db(root)
    callees = db.get_callees(sym_id, max_depth=depth)
    return _format_nodes(callees, f"Callees of {symbol}")


def handle_trace(arguments: Dict[str, Any], root: Path) -> Dict[str, Any]:
    from_sym = str(arguments.get("from", "")).strip()
    to_sym = str(arguments.get("to", "")).strip()
    if not from_sym or not to_sym:
        return {"error": "both 'from' and 'to' are required"}

    from_id = _find_symbol_id(from_sym, root)
    to_id = _find_symbol_id(to_sym, root)
    if not from_id:
        return {"error": f"Source symbol '{from_sym}' not found"}
    if not to_id:
        return {"error": f"Target symbol '{to_sym}' not found"}

    from .graph_db import get_db
    db = get_db(root)
    path = db.find_path(from_id, to_id, edge_kinds=["calls"], max_depth=7)

    if not path:
        return {
            "found": False,
            "from": from_sym,
            "to": to_sym,
            "message": (
                f"No direct call path from '{from_sym}' to '{to_sym}'. "
                "The connection likely breaks at dynamic dispatch (callback, DI, reflection, "
                "or interface/protocol resolution that static analysis cannot detect). "
                "Use aihelper_callers or aihelper_callees to trace one hop at a time."
            ),
        }

    return {
        "found": True,
        "from": from_sym,
        "to": to_sym,
        "path": [
            {
                "name": p.get("name", ""),
                "kind": p.get("kind", ""),
                "file": p.get("file_path", ""),
                "line": p.get("start_line", 0),
                "depth": p.get("depth", 0),
            }
            for p in path
        ],
    }


def handle_impact(arguments: Dict[str, Any], root: Path) -> Dict[str, Any]:
    symbol = str(arguments.get("symbol", "")).strip()
    if not symbol:
        return {"error": "symbol is required"}

    depth = int(arguments.get("depth") or 3)
    sym_id = _find_symbol_id(symbol, root)
    if not sym_id:
        return {"error": f"Symbol '{symbol}' not found in codebase"}

    from .graph_db import get_db
    db = get_db(root)
    impacted = db.get_impact_radius(sym_id, max_depth=depth)

    # Group by file
    files_affected = sorted(set(n.get("file_path", "") for n in impacted))
    risk = "low"
    if len(files_affected) > 20:
        risk = "critical"
    elif len(files_affected) > 10:
        risk = "high"
    elif len(files_affected) > 4:
        risk = "medium"

    return {
        "symbol": symbol,
        "impacted_count": len(impacted),
        "files_affected": len(files_affected),
        "risk_level": risk,
        "files": files_affected[:30],
        "results": _format_nodes(impacted, f"Impact of {symbol}"),
    }


def handle_explore(arguments: Dict[str, Any], root: Path) -> Dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return {"error": "query is required"}

    max_files = int(arguments.get("max_files") or 8)

    from .graph_db import get_db
    db = get_db(root)

    # Split query into tokens, search each
    tokens = [t.strip() for t in query.split() if len(t.strip()) >= 2]
    all_symbols: List[Dict] = []
    seen_ids: set = set()
    for token in tokens[:12]:
        results = db.search_symbols(token, limit=5)
        for r in results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                all_symbols.append(r)

    if not all_symbols:
        # Try regex fallback
        try:
            from .symbols import find_symbols
            for token in tokens[:5]:
                matches = find_symbols(token, root, limit=5)
                for m in matches.get("matches", []):
                    key = f"{m['file']}::{m['name']}"
                    if key not in seen_ids:
                        seen_ids.add(key)
                        all_symbols.append({"name": m["name"], "kind": m.get("kind", "symbol"),
                                            "file_path": m["file"],
                                            "start_line": m.get("line", 1),
                                            "end_line": m.get("line", 1),
                                            "id": key, "signature": m.get("signature", "")})
        except Exception:
            pass

    if not all_symbols:
        return {"error": f"No symbols found for '{query}'"}

    # Group by file
    by_file: Dict[str, List[Dict]] = {}
    for sym in all_symbols:
        fp = sym.get("file_path", "")
        if fp not in by_file:
            by_file[fp] = []
        by_file[fp].append(sym)

    # Read source for top N files
    result_files = []
    for fp, syms in list(by_file.items())[:max_files]:
        full_path = root / fp
        if not full_path.exists():
            continue

        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")
        except Exception:
            continue

        # Cluster symbols gần nhau
        syms_sorted = sorted(syms, key=lambda s: s.get("start_line", 1))
        clusters = _cluster_lines(syms_sorted, gap=12)
        sections = []
        for cluster in clusters:
            start = max(0, cluster["start"] - 4)
            end = min(len(lines), cluster["end"] + 4)
            section = "\n".join(
                f"{i+1}\t{lines[i]}" for i in range(start, end)
            )
            symbols_in = ", ".join(
                f"{s['name']}({s.get('kind', 'symbol')})" for s in cluster["symbols"]
            )
            language = _detect_lang(fp)
            sections.append(f"## {symbols_in}\n```{language}\n{section}\n```")

        result_files.append({
            "file": fp,
            "symbols": [s["name"] for s in syms],
            "source": "\n\n".join(sections),
        })

    return {
        "query": query,
        "total_symbols": len(all_symbols),
        "files_shown": len(result_files),
        "files": result_files,
    }


def _cluster_lines(symbols: List[Dict], gap: int = 12) -> List[Dict]:
    if not symbols:
        return []
    clusters = []
    current = {
        "start": symbols[0].get("start_line", 1),
        "end": symbols[0].get("end_line", symbols[0].get("start_line", 1)),
        "symbols": [symbols[0]],
    }
    for sym in symbols[1:]:
        sl = sym.get("start_line", 1)
        if sl <= current["end"] + gap:
            current["end"] = max(current["end"], sym.get("end_line", sl))
            current["symbols"].append(sym)
        else:
            clusters.append(current)
            current = {
                "start": sl,
                "end": sym.get("end_line", sl),
                "symbols": [sym],
            }
    clusters.append(current)
    return clusters


def _detect_lang(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    lang_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "tsx", ".java": "java", ".go": "go", ".rs": "rust",
        ".php": "php", ".c": "c", ".cpp": "cpp", ".rb": "ruby",
        ".swift": "swift", ".kt": "kotlin", ".cs": "csharp",
    }
    return lang_map.get(ext, "")
