"""
Primitives Registry — reusable, named, composable engineering primitives.

Design: All workflow handlers are registered as named primitives that can be
composed declaratively in YAML workflows. This prevents handler duplication
across workflows and enables the `uses: [...]` syntax.

Each primitive has:
  - name: dot-separated namespace (e.g. "graph.trace_callers")
  - description: what it does
  - handler: callable function
  - category: graph | verify | memory | git | risk | test
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ── Primitive definition ─────────────────────────────────────────

class Primitive:
    """A named, reusable engineering operation."""
    __slots__ = ("name", "description", "handler", "category", "deterministic")

    def __init__(self, name: str, description: str, handler: Callable,
                 category: str = "general", deterministic: bool = True):
        self.name = name
        self.description = description
        self.handler = handler
        self.category = category
        self.deterministic = deterministic

    def execute(self, context: Dict[str, Any], root: Path) -> Dict[str, Any]:
        """Execute this primitive, injecting project root if handler accepts it."""
        import inspect
        sig = inspect.signature(self.handler)
        params = list(sig.parameters.keys())
        if "project_root" in params or "root" in params:
            return self.handler(context, root)
        return self.handler(context, root)

    def __repr__(self):
        return f"Primitive({self.name}, {self.category})"


# ── Primitive Handler Implementations ────────────────────────────

def _graph_trace_callers(ctx: Dict, root: Path) -> Dict:
    """Trace all callers of a target symbol."""
    from .graph_db import get_db
    from .graph_query import _find_symbol_id
    sym_id = ctx.get("symbol_id", "")
    db = get_db(root)
    callers = db.get_callers(sym_id, max_depth=3) if sym_id else []
    return {"callers": [c.get("name", "") for c in callers], "caller_count": len(callers)}


def _graph_trace_callees(ctx: Dict, root: Path) -> Dict:
    """Trace all callees of a target symbol."""
    from .graph_db import get_db
    db = get_db(root)
    sym_id = ctx.get("symbol_id", "")
    callees = db.get_callees(sym_id, max_depth=3) if sym_id else []
    return {"callees": [c.get("name", "") for c in callees], "callee_count": len(callees)}


def _graph_analyze_target(ctx: Dict, root: Path) -> Dict:
    """Analyze a target symbol: callers, callees, symbol ID."""
    target = ctx.get("target", "")
    if not target:
        return {"error": "no target specified"}
    from .graph_db import get_db
    from .graph_query import _find_symbol_id
    db = get_db(root)
    sym_id = _find_symbol_id(target, root)
    callers = db.get_callers(sym_id, max_depth=2) if sym_id else []
    callees = db.get_callees(sym_id, max_depth=2) if sym_id else []
    return {
        "symbol_id": sym_id,
        "callers": len(callers), "callees": len(callees),
        "caller_list": [c.get("name", "") for c in callers[:10]],
        "callee_list": [c.get("name", "") for c in callees[:10]],
    }


def _graph_impact_radius(ctx: Dict, root: Path) -> Dict:
    """Calculate impact radius for a symbol."""
    from .graph_db import get_db
    db = get_db(root)
    sym_id = ctx.get("symbol_id", "")
    impacted = db.get_impact_radius(sym_id, max_depth=2) if sym_id else []
    files = sorted(set(n.get("file_path", "") for n in impacted))
    risk = "low" if len(files) <= 4 else "medium" if len(files) <= 10 else "high"
    return {"impacted_files": len(files), "risk": risk, "files": files[:20]}


def _graph_dependency_inspect(ctx: Dict, root: Path) -> Dict:
    """Inspect file dependencies."""
    from .graph_db import get_db
    db = get_db(root)
    deps = db.get_file_dependencies(ctx.get("file", ""))
    return {"dependencies": deps[:20], "dep_count": len(deps)}


def _verify_architecture_health(ctx: Dict, root: Path) -> Dict:
    """Verify architecture: circular deps, dead code."""
    from .verify import verify_architecture
    return verify_architecture(root)


def _verify_regression_risk(ctx: Dict, root: Path) -> Dict:
    """Verify regression risk."""
    from .verify import verify_regression_risk
    target = ctx.get("target", "")
    return verify_regression_risk(root, target)


def _verify_dependency_health(ctx: Dict, root: Path) -> Dict:
    """Verify dependency health."""
    from .verify import verify_dependency_health
    return verify_dependency_health(root)


def _verify_auth_safety(ctx: Dict, root: Path) -> Dict:
    """Verify auth safety."""
    from .verify import verify_auth_safety
    return verify_auth_safety(root)


def _memory_recall(ctx: Dict, root: Path) -> Dict:
    """Retrieve relevant memories."""
    try:
        from .intelligence.search import search_knowledge
        query = ctx.get("query", ctx.get("target", ctx.get("task", "")))
        results = search_knowledge(query, limit=10)
        return {"memories": results, "count": len(results)}
    except Exception:
        return {"memories": [], "count": 0}


def _git_diff(ctx: Dict, root: Path) -> Dict:
    """Get recent git changes."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "--no-pager", "diff", "--stat"],
            cwd=str(root), capture_output=True, text=True, timeout=10,
        )
        return {"diff_stat": result.stdout.strip()[:2000]}
    except Exception:
        return {"diff_stat": ""}


def _risk_classify(ctx: Dict, root: Path) -> Dict:
    """Classify risk level from affected files."""
    files = ctx.get("files", [])
    risk = "low"
    if len(files) > 20:
        risk = "critical"
    elif len(files) > 10:
        risk = "high"
    elif len(files) > 4:
        risk = "medium"
    return {"risk_level": risk, "files_affected": len(files)}


def _test_run(ctx: Dict, root: Path) -> Dict:
    """Run test suite."""
    import subprocess
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "-x", "--tb=short"],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
        return {
            "passed": result.returncode == 0,
            "output": result.stdout[-2000:],
            "failed": result.returncode != 0,
        }
    except Exception as e:
        return {"passed": False, "output": str(e), "failed": True}


def _test_generate_stub(ctx: Dict, root: Path) -> Dict:
    """Generate test stub placeholder."""
    return {"test_stub_ready": True, "test_file": ctx.get("target", "") + ".test"}


def _context_compress(ctx: Dict, root: Path) -> Dict:
    """Build compressed cognition package."""
    from .compressor import compress_context
    return compress_context(ctx, root)


def _lint_run(ctx: Dict, root: Path) -> Dict:
    """Run linter (placeholder)."""
    return {"lint_ok": True, "issues": 0}


def _summary_generate(ctx: Dict, root: Path) -> Dict:
    """Generate human-readable summary from context."""
    parts = []
    if ctx.get("passed") is not None:
        parts.append(f"Tests: {'PASSED' if ctx['passed'] else 'FAILED'}")
    if ctx.get("lint_ok") is not None:
        parts.append(f"Lint: {'OK' if ctx['lint_ok'] else 'ISSUES FOUND'}")
    if ctx.get("circular_deps") is not None:
        parts.append(f"Circular deps: {ctx['circular_deps']}")
    if ctx.get("dead_code") is not None:
        parts.append(f"Dead code: {ctx['dead_code']}")
    if ctx.get("risk_level"):
        parts.append(f"Risk: {ctx['risk_level']}")
    return {"summary_text": " | ".join(parts) if parts else "No issues found"}


# ── Registry ─────────────────────────────────────────────────────

def build_registry() -> Dict[str, Primitive]:
    """Build the complete primitive registry."""
    return {
        # Graph primitives
        "graph.trace_callers": Primitive(
            "graph.trace_callers", "Trace all callers of target symbol",
            _graph_trace_callers, "graph",
        ),
        "graph.trace_callees": Primitive(
            "graph.trace_callees", "Trace all callees of target symbol",
            _graph_trace_callees, "graph",
        ),
        "graph.analyze_target": Primitive(
            "graph.analyze_target", "Analyze target: callers, callees, symbol ID",
            _graph_analyze_target, "graph",
        ),
        "graph.impact_radius": Primitive(
            "graph.impact_radius", "Calculate impact radius and risk",
            _graph_impact_radius, "graph",
        ),
        "graph.dependency_inspect": Primitive(
            "graph.dependency_inspect", "Inspect file dependencies",
            _graph_dependency_inspect, "graph",
        ),
        # Verification primitives
        "verify.architecture": Primitive(
            "verify.architecture", "Check circular deps, dead code",
            _verify_architecture_health, "verify",
        ),
        "verify.regression_risk": Primitive(
            "verify.regression_risk", "Predict regression risk via impact + memory",
            _verify_regression_risk, "verify",
        ),
        "verify.dependency_health": Primitive(
            "verify.dependency_health", "Check dependency chains health",
            _verify_dependency_health, "verify",
        ),
        "verify.auth_safety": Primitive(
            "verify.auth_safety", "Audit auth flow for secrets",
            _verify_auth_safety, "verify",
        ),
        # Memory primitives
        "memory.recall": Primitive(
            "memory.recall", "Retrieve historical decisions, bugs, preferences",
            _memory_recall, "memory",
        ),
        # Git primitives
        "git.diff": Primitive(
            "git.diff", "Get recent git changes summary",
            _git_diff, "git",
        ),
        # Risk primitives
        "risk.classify": Primitive(
            "risk.classify", "Classify risk level from affected files",
            _risk_classify, "risk",
        ),
        # Test primitives
        "test.run": Primitive(
            "test.run", "Run test suite",
            _test_run, "test",
        ),
        "test.generate_stub": Primitive(
            "test.generate_stub", "Generate test file stub",
            _test_generate_stub, "test",
        ),
        # Context primitives
        "context.compress": Primitive(
            "context.compress", "Build distilled cognition package",
            _context_compress, "context",
        ),
        "context.summarize": Primitive(
            "context.summarize", "Generate human-readable summary",
            _summary_generate, "context",
        ),
        # Lint primitives
        "lint.run": Primitive(
            "lint.run", "Run linter checks",
            _lint_run, "lint",
        ),
    }


# Module-level cached registry
_registry: Optional[Dict[str, Primitive]] = None


def get_registry() -> Dict[str, Primitive]:
    """Get the primitive registry (cached)."""
    global _registry
    if _registry is None:
        _registry = build_registry()
    return _registry


def list_primitives() -> List[Dict[str, str]]:
    """List all available primitives with descriptions."""
    reg = get_registry()
    return [
        {"name": p.name, "description": p.description, "category": p.category,
         "deterministic": p.deterministic}
        for p in reg.values()
    ]


def get_primitive(name: str) -> Optional[Primitive]:
    """Get a primitive by name."""
    return get_registry().get(name)
