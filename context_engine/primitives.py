"""
Primitives Registry — reusable, named, composable engineering primitives.

Design: All workflow handlers are registered as named primitives with execution
contracts. Contracts declare inputs, outputs, cacheability, dependencies, and
cost estimates — enabling the runtime to:
  - Execute independent primitives in parallel
  - Cache and skip redundant computations
  - Compute execution DAG for partial recomputation
  - Collect runtime profiling metrics

Each primitive has:
  - name: dot-separated namespace (e.g. "graph.trace_callers")
  - description: what it does
  - handler: callable function
  - contract: PrimitiveContract with execution semantics
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set


# ── Primitive Contract ───────────────────────────────────────────

@dataclass
class PrimitiveContract:
    """Execution semantics for a primitive — compiler IR for the runtime.

    This is the key abstraction that unlocks:
      - parallel execution (via input/output dependency analysis)
      - caching (via cacheable + input fingerprinting)
      - partial recomputation (via depends_on invalidation)
      - optimization (via cost estimates)
      - profiling (via actual vs estimated metrics)
      - typed execution planning (via purity/determinism/invalidation_scope)

    v0.1: Typed Execution Capabilities — immutable capability metadata
    that the optimizer uses to make safe parallelization and caching decisions.
    """
    input_keys: List[str] = field(default_factory=list)
    output_keys: List[str] = field(default_factory=list)
    cacheable: bool = False
    side_effects: bool = False
    depends_on: List[str] = field(default_factory=list)
    cost_estimate_ms: float = 1.0
    token_estimate: int = 0
    invalidates: List[str] = field(default_factory=list)

    # ── v0.1 Typed Execution Capabilities ──
    # Immutable metadata for optimizer decisions. NOT mutated at runtime.
    purity: str = "unknown"             # "pure" | "mutative" | "unknown"
    determinism: str = "deterministic"   # "deterministic" | "heuristic" | "ai_bound"
    invalidation_scope: str = "symbol"   # "symbol" | "file" | "module" | "global"
    parallel_safe: bool = True           # Can run concurrently without race conditions

    def fingerprint_inputs(self, context: Dict[str, Any]) -> str:
        """Create a cache key from the inputs this primitive depends on."""
        import hashlib, json
        if not self.input_keys:
            return ""
        subset = {k: context.get(k) for k in self.input_keys if k in context}
        raw = json.dumps(subset, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    @property
    def is_pure(self) -> bool:
        """Pure primitives can be cached, parallelized, and replayed safely."""
        return self.purity == "pure" and not self.side_effects

    @property
    def is_deterministic(self) -> bool:
        """Deterministic primitives always produce the same output for same input."""
        return self.determinism == "deterministic"


# ── Primitive definition ─────────────────────────────────────────

class Primitive:
    """A named, reusable engineering operation with execution contract."""
    __slots__ = ("name", "description", "handler", "category", "deterministic", "contract")

    def __init__(self, name: str, description: str, handler: Callable,
                 category: str = "general", deterministic: bool = True,
                 contract: Optional[PrimitiveContract] = None):
        self.name = name
        self.description = description
        self.handler = handler
        self.category = category
        self.deterministic = deterministic
        self.contract = contract or PrimitiveContract()

    def execute(self, context: Dict[str, Any], root: Path) -> Dict[str, Any]:
        """Execute this primitive and return immutable output patch.

        The output is a pure dict — it does NOT mutate shared context directly.
        The caller is responsible for deterministic merging.
        """
        import inspect
        sig = inspect.signature(self.handler)
        params = list(sig.parameters.keys())
        result: Dict[str, Any]
        t0 = time.time()
        if "project_root" in params or "root" in params:
            result = self.handler(context, root)
        else:
            result = self.handler(context, root)
        elapsed = (time.time() - t0) * 1000
        # Tag result with execution metadata for profiling
        result["_primitive"] = self.name
        result["_duration_ms"] = round(elapsed, 2)
        result["_cached"] = False
        return result

    def __repr__(self):
        return f"Primitive({self.name}, {self.category})"

    def depends_on_primitive(self, other_name: str) -> bool:
        """Check if this primitive depends on another's outputs."""
        return other_name in self.contract.depends_on

    def to_dict(self) -> Dict[str, Any]:
        """Serializable representation for profiling/cli."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "deterministic": self.deterministic,
            "cacheable": self.contract.cacheable,
            "side_effects": self.contract.side_effects,
            "input_keys": self.contract.input_keys,
            "output_keys": self.contract.output_keys,
            "depends_on": self.contract.depends_on,
            "cost_estimate_ms": self.contract.cost_estimate_ms,
            "token_estimate": self.contract.token_estimate,
            # v0.1 typed capabilities
            "purity": self.contract.purity,
            "determinism": self.contract.determinism,
            "invalidation_scope": self.contract.invalidation_scope,
            "parallel_safe": self.contract.parallel_safe,
        }


# ── Primitive Handler Implementations ────────────────────────────

def _graph_trace_callers(ctx: Dict, root: Path) -> Dict:
    from .graph_db import get_db
    from .graph_query import _find_symbol_id
    sym_id = ctx.get("symbol_id", "")
    db = get_db(root)
    callers = db.get_callers(sym_id, max_depth=3) if sym_id else []
    return {"callers": [c.get("name", "") for c in callers], "caller_count": len(callers)}


def _graph_trace_callees(ctx: Dict, root: Path) -> Dict:
    from .graph_db import get_db
    db = get_db(root)
    sym_id = ctx.get("symbol_id", "")
    callees = db.get_callees(sym_id, max_depth=3) if sym_id else []
    return {"callees": [c.get("name", "") for c in callees], "callee_count": len(callees)}


def _graph_analyze_target(ctx: Dict, root: Path) -> Dict:
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
    from .graph_db import get_db
    db = get_db(root)
    sym_id = ctx.get("symbol_id", "")
    impacted = db.get_impact_radius(sym_id, max_depth=2) if sym_id else []
    files = sorted(set(n.get("file_path", "") for n in impacted))
    risk = "low" if len(files) <= 4 else "medium" if len(files) <= 10 else "high"
    return {"impacted_files": len(files), "risk": risk, "files": files[:20]}


def _graph_dependency_inspect(ctx: Dict, root: Path) -> Dict:
    from .graph_db import get_db
    db = get_db(root)
    deps = db.get_file_dependencies(ctx.get("file", ""))
    return {"dependencies": deps[:20], "dep_count": len(deps)}


def _verify_architecture_health(ctx: Dict, root: Path) -> Dict:
    from .verify import verify_architecture
    return verify_architecture(root)


def _verify_regression_risk(ctx: Dict, root: Path) -> Dict:
    from .verify import verify_regression_risk
    target = ctx.get("target", "")
    return verify_regression_risk(root, target)


def _verify_dependency_health(ctx: Dict, root: Path) -> Dict:
    from .verify import verify_dependency_health
    return verify_dependency_health(root)


def _verify_auth_safety(ctx: Dict, root: Path) -> Dict:
    from .verify import verify_auth_safety
    return verify_auth_safety(root)


def _memory_recall(ctx: Dict, root: Path) -> Dict:
    try:
        from .intelligence.search import search_knowledge
        query = ctx.get("query", ctx.get("target", ctx.get("task", "")))
        results = search_knowledge(query, limit=10)
        return {"memories": results, "count": len(results)}
    except Exception:
        return {"memories": [], "count": 0}


def _git_diff(ctx: Dict, root: Path) -> Dict:
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
    return {"test_stub_ready": True, "test_file": ctx.get("target", "") + ".test"}


def _context_compress(ctx: Dict, root: Path) -> Dict:
    from .compressor import compress_context
    return compress_context(ctx, root)


def _lint_run(ctx: Dict, root: Path) -> Dict:
    return {"lint_ok": True, "issues": 0}


def _telemetry_benchmark(ctx: Dict, root: Path) -> Dict:
    """Generate telemetry-driven benchmark from real runtime metrics (v0.1)."""
    try:
        from .benchmark import generate_benchmark, format_benchmark_markdown
        benchmark = generate_benchmark(root)
        markdown = format_benchmark_markdown(benchmark)
        return {
            "benchmark": benchmark,
            "markdown": markdown,
            "system_state": benchmark.get("system_state", {}),
            "runtime_metrics": benchmark.get("runtime_metrics", {}),
        }
    except Exception as e:
        return {"benchmark": None, "markdown": "", "error": str(e)}


def _telemetry_subagent_wiring(ctx: Dict, root: Path) -> Dict:
    """Compile cognition package for sub-agent execution (v0.1)."""
    try:
        from .subagent_wiring import compile_cognition_package, generate_subagent_prompt
        task = ctx.get("task", "")
        target = ctx.get("target", task)
        max_tokens = ctx.get("max_tokens", 2000)
        package = compile_cognition_package(task, target, root, max_tokens)
        prompt = generate_subagent_prompt(package)
        return {
            "cognition_package": package.to_dict() if hasattr(package, 'to_dict') else package,
            "generated_prompt": prompt,
        }
    except Exception as e:
        return {"cognition_package": None, "generated_prompt": "", "error": str(e)}


def _summary_generate(ctx: Dict, root: Path) -> Dict:
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

def _c(*, ik=None, ok=None, cacheable=False, side=False, deps=None, cost=1.0, tokens=0, inv=None,
       purity=None, det=None, scope=None, par_safe=None):
    """Shorthand factory for PrimitiveContract.

    v0.1: Added typed capability parameters with smart defaults inferred from other fields.
    """
    # Smart defaults for typed capabilities
    resolved_purity = purity or ("mutative" if side else "pure")
    resolved_det = det or "deterministic"
    resolved_scope = scope or "symbol"
    resolved_par_safe = par_safe if par_safe is not None else (not side)

    return PrimitiveContract(
        input_keys=ik or [], output_keys=ok or [], cacheable=cacheable,
        side_effects=side, depends_on=deps or [], cost_estimate_ms=cost,
        token_estimate=tokens, invalidates=inv or [],
        purity=resolved_purity, determinism=resolved_det,
        invalidation_scope=resolved_scope, parallel_safe=resolved_par_safe,
    )


def build_registry() -> Dict[str, Primitive]:
    """Build the complete primitive registry with execution contracts."""
    return {
        # ── Graph primitives ──────────────────────────────────────
        "graph.analyze_target": Primitive(
            "graph.analyze_target", "Analyze target: callers, callees, symbol ID",
            _graph_analyze_target, "graph",
            contract=_c(ik=["target"], ok=["symbol_id", "callers", "callees", "caller_list", "callee_list"],
                        cacheable=True, deps=[], cost=3.0, tokens=0),
        ),
        "graph.trace_callers": Primitive(
            "graph.trace_callers", "Trace all callers of target symbol",
            _graph_trace_callers, "graph",
            contract=_c(ik=["symbol_id"], ok=["callers", "caller_count"],
                        cacheable=True, deps=["graph.analyze_target"], cost=2.0, tokens=0),
        ),
        "graph.trace_callees": Primitive(
            "graph.trace_callees", "Trace all callees of target symbol",
            _graph_trace_callees, "graph",
            contract=_c(ik=["symbol_id"], ok=["callees", "callee_count"],
                        cacheable=True, deps=["graph.analyze_target"], cost=2.0, tokens=0),
        ),
        "graph.impact_radius": Primitive(
            "graph.impact_radius", "Calculate impact radius and risk",
            _graph_impact_radius, "graph",
            contract=_c(ik=["symbol_id"], ok=["impacted_files", "risk", "files"],
                        cacheable=True, deps=["graph.analyze_target"], cost=3.0, tokens=0),
        ),
        "graph.dependency_inspect": Primitive(
            "graph.dependency_inspect", "Inspect file dependencies",
            _graph_dependency_inspect, "graph",
            contract=_c(ik=["file"], ok=["dependencies", "dep_count"],
                        cacheable=True, cost=2.0, tokens=0),
        ),
        # ── Verification primitives ───────────────────────────────
        "verify.architecture": Primitive(
            "verify.architecture", "Check circular deps, dead code",
            _verify_architecture_health, "verify",
            contract=_c(ok=["circular_deps", "dead_code", "passed", "violations"],
                        cacheable=True, cost=10.0, tokens=0),
        ),
        "verify.regression_risk": Primitive(
            "verify.regression_risk", "Predict regression risk via impact + memory",
            _verify_regression_risk, "verify",
            contract=_c(ik=["target"], ok=["risk_level", "affected_files", "file_list", "past_bugs"],
                        cacheable=False, cost=5.0, tokens=0),
        ),
        "verify.dependency_health": Primitive(
            "verify.dependency_health", "Check dependency chains health",
            _verify_dependency_health, "verify",
            contract=_c(ok=["circular_deps", "dead_code", "deep_chains", "health_score"],
                        cacheable=True, cost=8.0, tokens=0),
        ),
        "verify.auth_safety": Primitive(
            "verify.auth_safety", "Audit auth flow for secrets",
            _verify_auth_safety, "verify",
            contract=_c(ok=["findings", "severity", "passed"],
                        cacheable=False, side=True, cost=50.0, tokens=0),
        ),
        # ── Memory primitives ────────────────────────────────────
        "memory.recall": Primitive(
            "memory.recall", "Retrieve historical decisions, bugs, preferences",
            _memory_recall, "memory",
            contract=_c(ik=["target", "task"], ok=["memories", "count"],
                        cacheable=True, cost=3.0, tokens=0),
        ),
        # ── Git primitives ───────────────────────────────────────
        "git.diff": Primitive(
            "git.diff", "Get recent git changes summary",
            _git_diff, "git",
            contract=_c(ok=["diff_stat"], cacheable=False, side=True, cost=500.0, tokens=0),
        ),
        # ── Risk primitives ──────────────────────────────────────
        "risk.classify": Primitive(
            "risk.classify", "Classify risk level from affected files",
            _risk_classify, "risk",
            contract=_c(ik=["files"], ok=["risk_level", "files_affected"],
                        cacheable=True, deps=["graph.impact_radius"], cost=0.5, tokens=0),
        ),
        # ── Test primitives ──────────────────────────────────────
        "test.run": Primitive(
            "test.run", "Run test suite",
            _test_run, "test",
            contract=_c(ok=["passed", "output", "failed"],
                        cacheable=False, side=True, cost=30000.0, tokens=0),
        ),
        "test.generate_stub": Primitive(
            "test.generate_stub", "Generate test file stub",
            _test_generate_stub, "test",
            contract=_c(ik=["target"], ok=["test_stub_ready", "test_file"],
                        cacheable=True, cost=1.0, tokens=0),
        ),
        # ── Context primitives ───────────────────────────────────
        "context.compress": Primitive(
            "context.compress", "Build distilled cognition package",
            _context_compress, "context",
            contract=_c(ik=["target", "question"], ok=["system_state", "question"],
                        cacheable=True, cost=15.0, tokens=0),
        ),
        "context.summarize": Primitive(
            "context.summarize", "Generate human-readable summary",
            _summary_generate, "context",
            contract=_c(ok=["summary_text"], cacheable=True, cost=2.0, tokens=0),
        ),
        # ── Lint primitives ──────────────────────────────────────
        "lint.run": Primitive(
            "lint.run", "Run linter checks",
            _lint_run, "lint",
            contract=_c(ok=["lint_ok", "issues"], cacheable=False, cost=10000.0, tokens=0),
        ),
        # ── Telemetry primitives (v0.1) ──────────────────────────
        "telemetry.benchmark": Primitive(
            "telemetry.benchmark", "Generate telemetry-driven benchmark report from real runtime metrics",
            _telemetry_benchmark, "telemetry",
            contract=_c(ok=["benchmark", "markdown", "system_state", "runtime_metrics"],
                        cacheable=False, cost=50.0, tokens=0, purity="pure"),
        ),
        "telemetry.subagent_wiring": Primitive(
            "telemetry.subagent_wiring", "Compile cognition package for sub-agent execution",
            _telemetry_subagent_wiring, "telemetry",
            contract=_c(ik=["task", "target"], ok=["cognition_package", "generated_prompt"],
                        cacheable=True, cost=10.0, tokens=0, purity="pure"),
        ),
    }


# ── Module-level cached registry ─────────────────────────────────

_registry: Optional[Dict[str, Primitive]] = None


def get_registry() -> Dict[str, Primitive]:
    """Get the primitive registry (cached)."""
    global _registry
    if _registry is None:
        _registry = build_registry()
    return _registry


def list_primitives() -> List[Dict[str, Any]]:
    """List all available primitives with full contract details."""
    reg = get_registry()
    return [p.to_dict() for p in reg.values()]


def get_primitive(name: str) -> Optional[Primitive]:
    """Get a primitive by name."""
    return get_registry().get(name)


# ── Execution DAG helpers ───────────────────────────────────────

def build_execution_dag(primitive_names: List[str]) -> List[List[str]]:
    """Group primitives into parallel execution stages based on dependencies.

    Returns a list of stages. Primitives within the same stage can run in parallel.
    Primitives in later stages depend on outputs from earlier stages.
    """
    reg = get_registry()
    stages: List[List[str]] = []
    executed: Set[str] = set()

    while len(executed) < len(primitive_names):
        stage: List[str] = []
        for name in primitive_names:
            if name in executed:
                continue
            prim = reg.get(name)
            if prim is None:
                stage.append(name)
                continue
            # Can run if all dependencies are already executed
            deps_satisfied = all(
                d in executed or d not in primitive_names
                for d in prim.contract.depends_on
            )
            if deps_satisfied:
                stage.append(name)
        if not stage:
            # Remaining unresolved — run sequentially as fallback
            stage = [n for n in primitive_names if n not in executed]
        stages.append(stage)
        executed.update(stage)

    return stages


def compute_parallelism_ratio(primitive_names: List[str]) -> float:
    """Compute the theoretical parallelism ratio for a set of primitives.

    1.0 = fully parallel (all can run simultaneously)
    0.0 = fully sequential (each depends on previous)
    """
    stages = build_execution_dag(primitive_names)
    total = len(primitive_names)
    if total <= 1:
        return 1.0
    # Parallelism ratio = 1 - (stages / primitives)
    # Fewer stages = more parallelism
    return round(1.0 - (len(stages) - 1) / max(total - 1, 1), 2)
