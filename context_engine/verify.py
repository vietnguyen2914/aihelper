"""
Verification Runtime — reusable architecture, auth, regression, and dependency checks.
All deterministic. Zero AI tokens.

Commands:
  aihelper verify architecture
  aihelper verify auth-safety
  aihelper verify regression-risk [--target SYMBOL]
  aihelper verify dependency-health
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List


def verify_architecture(project_root: Path) -> Dict[str, Any]:
    """Check architectural rules: circular deps, dead code, module boundaries."""
    from .graph_db import get_db
    db = get_db(project_root)

    circular = db.find_circular_deps()
    dead = db.find_dead_code()
    stats = db.get_stats()

    violations = []
    if circular:
        violations.append(f"{len(circular)} circular dependency cycles found")
    if dead:
        violations.append(f"{len(dead)} potentially dead symbols")

    return {
        "check": "architecture",
        "passed": len(violations) == 0,
        "violations": violations,
        "circular_deps": circular[:20],
        "dead_code": dead[:20],
        "symbol_count": stats.get("symbol_count", 0),
        "file_count": stats.get("file_count", 0),
        "deterministic": True,
        "tokens_used": 0,
    }


def verify_auth_safety(project_root: Path) -> Dict[str, Any]:
    """Audit auth flow safety: check for hardcoded secrets, missing validation."""
    findings = []
    secret_patterns = [
        (r'(?:password|secret|token|key|api_key)\s*=\s*["\'][^"\']{4,}["\']', "hardcoded_secret"),
        (r'(?:TODO|FIXME|HACK).*auth', "auth_todo"),
        (r'console\.log\(.*(?:token|password|secret)', "leaked_credential"),
    ]

    for py_file in list(project_root.rglob("*.py"))[:500]:
        try:
            content = py_file.read_text(errors="ignore")
        except Exception:
            continue
        for pattern, kind in secret_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for m in matches[:5]:
                masked = re.sub(r'["\'](.+)["\']', '"***"', str(m))
                findings.append({
                    "file": str(py_file.relative_to(project_root)),
                    "type": kind,
                    "match": masked,
                })

    return {
        "check": "auth_safety",
        "passed": len(findings) == 0,
        "findings": findings[:30],
        "severity": "critical" if len(findings) > 5 else "warning" if findings else "clean",
        "deterministic": True,
        "tokens_used": 0,
    }


def verify_regression_risk(project_root: Path, target: str = "") -> Dict[str, Any]:
    """Predict regression risk for a change using impact graph + memory."""
    from .graph_db import get_db
    from .graph_query import _find_symbol_id

    db = get_db(project_root)
    sym_id = _find_symbol_id(target, project_root) if target else None
    impacted = db.get_impact_radius(sym_id, max_depth=3) if sym_id else []
    files = sorted(set(n.get("file_path", "") for n in impacted))

    try:
        from .intelligence.search import search_knowledge
        past_bugs_raw = search_knowledge(target, limit=5) if target else []
        # Normalize: search_knowledge may return strings or dicts
        past_bugs = []
        if isinstance(past_bugs_raw, list):
            for b in past_bugs_raw:
                if isinstance(b, dict):
                    past_bugs.append(b)
                elif isinstance(b, str):
                    past_bugs.append({"symptom": b, "fix": ""})
    except Exception:
        past_bugs = []

    risk = "low"
    if len(files) > 20 or len(past_bugs) > 3:
        risk = "critical"
    elif len(files) > 10 or len(past_bugs) > 1:
        risk = "high"
    elif len(files) > 4:
        risk = "medium"

    safe_bugs = []
    for b in past_bugs:
        if isinstance(b, dict):
            safe_bugs.append({
                "symptom": b.get("symptom", str(b)),
                "fix": b.get("fix", b.get("fix_commit", "")),
            })
        else:
            safe_bugs.append({"symptom": str(b), "fix": ""})

    return {
        "check": "regression_risk",
        "target": target or "(full codebase)",
        "risk_level": risk,
        "affected_files": len(files),
        "file_list": files[:30],
        "past_bugs": safe_bugs,
        "deterministic": True,
        "tokens_used": 0,
    }


def verify_dependency_health(project_root: Path) -> Dict[str, Any]:
    """Check dependency health: circular deps, orphaned deps, deep chains."""
    from .graph_db import get_db
    db = get_db(project_root)

    circular = db.find_circular_deps()
    dead = db.find_dead_code()
    all_files = db.get_all_files()

    deep_chains = []
    for f in all_files[:100]:
        deps = db.get_file_dependencies(f.get("path", ""))
        if len(deps) > 15:
            deep_chains.append({"file": f.get("path", ""), "dep_count": len(deps)})

    return {
        "check": "dependency_health",
        "passed": len(circular) == 0 and len(deep_chains) == 0,
        "circular_deps": len(circular),
        "dead_code": len(dead),
        "deep_chains": deep_chains[:20],
        "health_score": "good" if len(circular) == 0 and len(deep_chains) < 5 else "needs_attention",
        "deterministic": True,
        "tokens_used": 0,
    }


# ── Verification registry ───────────────────────────────────────

VERIFICATION_CHECKS = {
    "architecture": verify_architecture,
    "auth-safety": verify_auth_safety,
    "regression-risk": verify_regression_risk,
    "dependency-health": verify_dependency_health,
}


def handle_verify(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run a verification check."""
    check_name = params.get("check", params.get("name", ""))
    project_root = Path(params.get("project_root", str(Path.cwd())))
    target = params.get("target", "")

    if check_name not in VERIFICATION_CHECKS:
        return {
            "error": f"Unknown check: {check_name}",
            "available": list(VERIFICATION_CHECKS.keys()),
        }

    fn = VERIFICATION_CHECKS[check_name]
    if check_name == "regression-risk" and target:
        result = fn(project_root, target)
    else:
        result = fn(project_root)

    return result
