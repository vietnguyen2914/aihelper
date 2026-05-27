"""
Optimizer — cognition compilation optimization passes.

Separate layer that optimizes the primitive execution DAG before execution.
Inspired by compiler backend architecture: deduplication, constant folding,
dead branch pruning.

Philosophy: optimization logic lives here, NOT in workflow engine or cache.
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from .primitives import Primitive, get_primitive


def optimize_dag(primitive_names: List[str],
                 context: Dict[str, Any],
                 primitive_cache: Dict[str, Dict[str, Any]]) -> List[str]:
    """Run all optimization passes on a list of primitive names.

    Returns optimized list of primitives to execute.
    """
    result = list(primitive_names)

    # Pass 1: Deduplication
    result = deduplicate_pass(result)

    # Pass 2: Constant folding (cache hits)
    result = constant_folding_pass(result, context, primitive_cache)

    # No dead branch pruning here — that's at the DAG stage level in engine

    return result


# ── Optimization Passes ────────────────────────────────────────

def deduplicate_pass(primitive_names: List[str]) -> List[str]:
    """Remove duplicate primitive calls in the same execution.

    If the same primitive appears twice, keep only the first occurrence.
    """
    seen: Set[str] = set()
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

        if prim.contract.cacheable:
            fp = prim.contract.fingerprint_inputs(context)
            if fp:
                cache_key = f"{name}:{fp}"
                if cache_key in cache:
                    # Cache hit — skip this primitive
                    continue

        result.append(name)

    return result


def fold_count(primitive_names: List[str], context: Dict[str, Any],
               cache: Dict[str, Dict[str, Any]]) -> int:
    """Count how many primitives can be constant-folded."""
    folded = 0
    for name in primitive_names:
        prim = get_primitive(name)
        if prim is None:
            continue
        if prim.contract.cacheable:
            fp = prim.contract.fingerprint_inputs(context)
            if fp and f"{name}:{fp}" in cache:
                folded += 1
    return folded


def prune_dead_branches(primitive_names: List[str],
                        failed_gate: str) -> List[str]:
    """Remove primitives that depend on a failed gate."""
    # Simple: remove all primitives after the failed gate
    if failed_gate in primitive_names:
        idx = primitive_names.index(failed_gate)
        # Keep everything up to and including the failed gate
        # Only prune independent branches — simplified
        return primitive_names[:idx + 1]
    return primitive_names


def optimize_report(primitive_names: List[str],
                    context: Dict[str, Any],
                    cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Generate an optimization report for debugging."""
    original = len(primitive_names)
    deduped = deduplicate_pass(primitive_names)
    folded = constant_folding_pass(deduped, context, cache)

    return {
        "original_count": original,
        "after_dedup": len(deduped),
        "after_folding": len(folded),
        "duplicates_removed": original - len(deduped),
        "cache_hits": len(deduped) - len(folded),
        "primitives_executed": folded,
        "optimization_ratio": round(len(folded) / max(original, 1), 2),
    }
