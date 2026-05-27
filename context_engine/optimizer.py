"""
Optimizer — cognition compilation optimization passes.

Separate layer that optimizes the primitive execution DAG before execution.
Inspired by compiler backend architecture: deduplication, constant folding,
dead branch pruning.

Philosophy: optimization logic lives here, NOT in workflow engine or cache.

v0.1: Typed capabilities integration — optimizer uses purity/determinism/
invalidation_scope to make safe decisions. Optimizer remains PURE:
no filesystem mutation, no graph mutation, no cache mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .primitives import get_primitive


@dataclass
class OptimizationResult:
    """Result of running optimization passes on a primitive DAG.

    Provides full transparency into what the optimizer did — essential
    for profiling, debugging, and observability.
    """
    optimized_dag: List[str]
    original_count: int
    optimized_count: int
    applied_passes: List[str] = field(default_factory=list)
    folded_nodes: List[str] = field(default_factory=list)
    cache_hits: List[str] = field(default_factory=list)
    eliminated_nodes: List[str] = field(default_factory=list)
    estimated_speedup: float = 1.0

    @property
    def optimization_ratio(self) -> float:
        return round(self.optimized_count / max(self.original_count, 1), 2)

    @property
    def is_noop(self) -> bool:
        return self.original_count == self.optimized_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "optimized_dag": self.optimized_dag,
            "original_count": self.original_count,
            "optimized_count": self.optimized_count,
            "optimization_ratio": self.optimization_ratio,
            "applied_passes": self.applied_passes,
            "folded_nodes": self.folded_nodes,
            "cache_hits": self.cache_hits,
            "eliminated_nodes": self.eliminated_nodes,
            "estimated_speedup": round(self.estimated_speedup, 2),
        }


def optimize_dag(primitive_names: List[str],
                 context: Dict[str, Any],
                 primitive_cache: Dict[str, Dict[str, Any]]) -> OptimizationResult:
    """Run all optimization passes on a list of primitive names.

    Returns an OptimizationResult with the optimized DAG and detailed
    pass information for profiling.

    Passes run in order:
      1. Deduplication — remove duplicate primitives
      2. Constant folding — skip cacheable primitives with cache hits
      3. Purity check — validate parallel_safe before DAG staging
    """
    original = list(primitive_names)
    applied_passes: List[str] = []
    folded_nodes: List[str] = []
    cache_hit_nodes: List[str] = []
    eliminated_nodes: List[str] = []

    # Pass 1: Deduplication
    result = deduplicate_pass(original)
    if len(result) < len(original):
        applied_passes.append("deduplication")
        # Track eliminated duplicates by counting occurrences
        from collections import Counter
        orig_counts = Counter(original)
        result_counts = Counter(result)
        for name, count in orig_counts.items():
            removed = count - result_counts.get(name, 0)
            for _ in range(removed):
                eliminated_nodes.append(name)

    # Pass 2: Constant folding (cache hits)
    result, folded = constant_folding_pass_with_report(result, context, primitive_cache)
    if folded:
        applied_passes.append("constant_folding")
        folded_nodes.extend(folded)
        cache_hit_nodes.extend(folded)

    # Pass 3: Purity verification — flag mutative primitives that can't parallelize
    purity_issues = _check_purity_safety(result)
    if not purity_issues:
        applied_passes.append("purity_check_passed")

    # Calculate estimated speedup
    estimated_speedup = _estimate_speedup(original, result, primitive_cache, context)

    return OptimizationResult(
        optimized_dag=result,
        original_count=len(original),
        optimized_count=len(result),
        applied_passes=applied_passes,
        folded_nodes=folded_nodes,
        cache_hits=cache_hit_nodes,
        eliminated_nodes=eliminated_nodes,
        estimated_speedup=estimated_speedup,
    )


# ── Optimization Passes ────────────────────────────────────────

def deduplicate_pass(primitive_names: List[str]) -> List[str]:
    """Remove duplicate primitive calls in the same execution.

    If the same primitive appears twice, keep only the first occurrence.
    Pure function — no side effects.
    """
    seen: set[str] = set()
    result = []
    for name in primitive_names:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def constant_folding_pass(primitive_names: List[str],
                          context: Dict[str, Any],
                          cache: Dict[str, Dict[str, Any]]) -> List[str]:
    """Remove primitives whose inputs haven't changed and results are cached.

    If a cacheable primitive has a cache hit for its current inputs,
    remove it from execution — the cached result will be merged at runtime.
    """
    result = []
    for name in primitive_names:
        prim = get_primitive(name)
        if prim is None:
            result.append(name)
            continue

        if prim.contract.cacheable and prim.contract.is_pure:
            fp = prim.contract.fingerprint_inputs(context)
            if fp:
                cache_key = f"{name}:{fp}"
                if cache_key in cache:
                    # Cache hit — skip this primitive
                    continue

        result.append(name)

    return result


def constant_folding_pass_with_report(primitive_names: List[str],
                                       context: Dict[str, Any],
                                       cache: Dict[str, Dict[str, Any]]) -> tuple[List[str], List[str]]:
    """Constant folding pass that also reports which nodes were folded."""
    result = []
    folded = []
    for name in primitive_names:
        prim = get_primitive(name)
        if prim is None:
            result.append(name)
            continue

        if prim.contract.cacheable and prim.contract.is_pure:
            fp = prim.contract.fingerprint_inputs(context)
            if fp:
                cache_key = f"{name}:{fp}"
                if cache_key in cache:
                    folded.append(name)
                    continue

        result.append(name)

    return result, folded


def fold_count(primitive_names: List[str], context: Dict[str, Any],
               cache: Dict[str, Dict[str, Any]]) -> int:
    """Count how many primitives can be constant-folded."""
    folded = 0
    for name in primitive_names:
        prim = get_primitive(name)
        if prim is None:
            continue
        if prim.contract.cacheable and prim.contract.is_pure:
            fp = prim.contract.fingerprint_inputs(context)
            if fp and f"{name}:{fp}" in cache:
                folded += 1
    return folded


def prune_dead_branches(primitive_names: List[str],
                        failed_gate: str) -> List[str]:
    """Remove primitives that depend on a failed gate."""
    if failed_gate in primitive_names:
        idx = primitive_names.index(failed_gate)
        return primitive_names[:idx + 1]
    return primitive_names


# ── v0.1: Purity-aware checks ─────────────────────────────────

def _check_purity_safety(primitive_names: List[str]) -> List[str]:
    """Verify all primitives in the DAG are safe to execute together.

    Returns list of issues (empty = all good). Does NOT mutate anything.
    """
    issues = []
    for name in primitive_names:
        prim = get_primitive(name)
        if prim is None:
            continue
        if not prim.contract.parallel_safe:
            issues.append(f"{name}: not parallel_safe")
        if prim.contract.purity == "mutative" and prim.contract.side_effects:
            # Mutative primitives are valid, just noted
            pass
    return issues


def is_parallel_safe(primitive_names: List[str]) -> bool:
    """Check if all primitives in a DAG stage can run in parallel."""
    for name in primitive_names:
        prim = get_primitive(name)
        if prim and not prim.contract.parallel_safe:
            return False
    return True


def _estimate_speedup(original: List[str], optimized: List[str],
                      cache: Dict[str, Dict[str, Any]],
                      context: Dict[str, Any]) -> float:
    """Estimate speedup from optimization using cost metadata."""
    def _cost(name: str) -> float:
        p = get_primitive(name)
        return p.contract.cost_estimate_ms if p else 0.0

    total_original_cost = sum(_cost(n) for n in original) or 1.0
    total_optimized_cost = sum(_cost(n) for n in optimized) or 1.0

    # Account for cache hits: they cost ~0ms
    cache_hit_count = len(original) - len(optimized)
    total_optimized_cost += cache_hit_count * 0.01  # cache lookup ~0.01ms

    return round(total_original_cost / max(total_optimized_cost, 0.01), 2)


# ── Optimization Report ────────────────────────────────────────

def optimize_report(primitive_names: List[str],
                    context: Dict[str, Any],
                    cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Generate an optimization report for debugging."""
    result = optimize_dag(primitive_names, context, cache)
    return {
        **result.to_dict(),
        "purity_issues": _check_purity_safety(primitive_names),
        "parallel_safe": is_parallel_safe(primitive_names),
    }
