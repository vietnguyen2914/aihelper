"""
Context Compressor — builds distilled cognition packages for frontier models.

Instead of sending raw files, aihelper compresses repository state into
a structured JSON that maximizes the frontier model's reasoning density.

Principle: frontier models should consume KNOWLEDGE GRAPHS, not raw repositories.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

# Incremental compression cache
_compression_cache: Dict[str, Dict[str, Any]] = {}


def compress_context(context: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    """Compress context with incremental caching."""
    target = context.get("target", context.get("question", ""))
    if target:
        import hashlib
        ck = hashlib.md5(target.encode()).hexdigest()[:12]
        if ck in _compression_cache:
            return _compression_cache[ck]

    package = {
        "system_state": {
            "architecture": _extract_architecture(context, project_root),
            "historical_failures": _extract_historical_failures(context),
            "current_change": _extract_current_change(context),
            "affected_graph": _extract_affected_graph(context, project_root),
            "risks": _extract_risks(context),
        },
        "question": context.get("question", context.get("task", "")),
    }

    if target:
        import hashlib
        _compression_cache[hashlib.md5(target.encode()).hexdigest()[:12]] = package

    return package


def estimate_token_count(package: Dict[str, Any]) -> int:
    """Rough token count estimate (~4 chars per token)."""
    import json
    raw = json.dumps(package, default=str)
    return len(raw) // 4


def _extract_architecture(context: Dict, root: Path) -> Dict:
    from .graph_db import get_db
    db = get_db(root)
    stats = db.get_stats()
    return {
        "symbol_count": stats.get("symbol_count", 0),
        "file_count": stats.get("file_count", 0),
        "top_level_modules": list(context.get("modules", {}).keys())[:10],
        "hot_paths": context.get("hot_paths", []),
        "description": context.get("architecture_description", ""),
    }


def _extract_historical_failures(context: Dict) -> List[Dict]:
    memories = context.get("memories", [])
    failures = []
    for m in memories:
        if isinstance(m, dict):
            failures.append({
                "symptom": m.get("symptom", m.get("description", "")),
                "root_cause": m.get("root_cause", ""),
                "fix": m.get("fix", m.get("fix_commit", "")),
                "modules": m.get("affected_modules", []),
            })
    return failures[:10]


def _extract_current_change(context: Dict) -> Dict:
    return {
        "description": context.get("task", context.get("target", "")),
        "files_changed": context.get("files", [])[:20],
        "diff_summary": context.get("diff_stat", ""),
    }


def _extract_affected_graph(context: Dict, root: Path) -> Dict:
    from .graph_db import get_db
    from .graph_query import _find_symbol_id

    sym = context.get("target", "")
    if not sym:
        return {"nodes": [], "edges": 0}

    db = get_db(root)
    sym_id = _find_symbol_id(sym, root)
    callers = db.get_callers(sym_id, max_depth=2) if sym_id else []
    callees = db.get_callees(sym_id, max_depth=2) if sym_id else []

    return {
        "target": sym,
        "callers": [c.get("name", "") for c in callers[:15]],
        "callees": [c.get("name", "") for c in callees[:15]],
        "total_callers": len(callers),
        "total_callees": len(callees),
    }


def _extract_risks(context: Dict) -> List[Dict]:
    risks = []
    if context.get("circular_deps"):
        risks.append({"type": "circular_dependency",
                       "count": len(context["circular_deps"])})
    if context.get("dead_code"):
        risks.append({"type": "dead_code",
                       "count": len(context["dead_code"])})
    if context.get("risk_level"):
        risks.append({"type": "impact_risk", "level": context["risk_level"]})

    memories = context.get("memories", [])
    if len(memories) > 0:
        risks.append({"type": "historical_recurrence",
                       "past_incidents": len(memories)})

    return risks


# ── Daemon handler ──────────────────────────────────────────────

def handle_compress_context(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build compressed context package."""
    question = params.get("question", params.get("task", ""))
    target = params.get("target", "")
    project_root = Path(params.get("project_root", str(Path.cwd())))

    from .graph_db import get_db
    from .graph_query import _find_symbol_id

    ctx = {"question": question, "target": target}

    db = get_db(project_root)
    if target:
        sym_id = _find_symbol_id(target, project_root)
        if sym_id:
            ctx["symbol_id"] = sym_id
            ctx["callers"] = db.get_callers(sym_id, max_depth=2)
            ctx["callees"] = db.get_callees(sym_id, max_depth=2)

    try:
        from .intelligence.search import search_knowledge
        ctx["memories"] = search_knowledge(question or target, limit=10)
    except Exception:
        ctx["memories"] = []

    ctx["circular_deps"] = db.find_circular_deps()
    ctx["dead_code"] = db.find_dead_code()

    package = compress_context(ctx, project_root)
    package["estimated_tokens"] = estimate_token_count(package)

    return package
