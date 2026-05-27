#!/usr/bin/env python3
"""benchmark.py — aihelper benchmarks (v0.1 updated).

Runs benchmarks across projects under ~/github (or --project-root).
4 runs per metric, median reported.

v0.1 additions:
  - Typed capability distribution
  - Optimizer performance (dedup + constant folding + purity)
  - DAG build + parallelism ratio
  - Semantic invalidation: classify_change + weighted decay
  - Compression confidence decay chain
  - Signature extraction speed

Usage:
  python3 scripts/benchmark.py                        # all projects under ~/github
  python3 scripts/benchmark.py --project-root .        # this project only
  python3 scripts/benchmark.py --runs 8 --json         # 8 runs, JSON output
  python3 scripts/benchmark.py --quick                 # fast v0.1-only metrics
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

GITHUB_ROOT = Path.home() / "github"
WARMUP = 1
_PROJECT_SELF = Path(__file__).resolve().parent.parent


def median(vals: List[float]) -> float:
    return statistics.median(vals) if vals else 0.0


def timed(func, runs: int = 4, warmup: int = 1) -> Dict[str, float]:
    for _ in range(warmup):
        func()
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        func()
        times.append((time.perf_counter() - t0) * 1000)
    return {
        "min_ms": round(min(times), 3),
        "max_ms": round(max(times), 3),
        "median_ms": round(median(times), 3),
        "runs": runs,
    }


def discover_projects() -> List[Path]:
    roots = []
    if GITHUB_ROOT.exists():
        for d in sorted(GITHUB_ROOT.iterdir()):
            if d.is_dir() and (d / ".git").exists():
                roots.append(d)
    return roots


# ── Classic Benchmarks (v0.0.7 compatible) ───────────────────────

def bench_classic(root: Path, runs: int) -> Dict[str, Any]:
    """Run classic cache/build/graph benchmarks."""
    sys.path.insert(0, str(_PROJECT_SELF))
    from context_engine.cache import build_cache, clean_cache
    from context_engine.graph_db import get_db
    from context_engine.symbols import find_symbols

    clean_cache(root)
    build = timed(lambda: build_cache(root), runs=runs)

    db = get_db(root)
    stats = db.get_stats()

    queries = [
        "main", "build", "cache", "handle", "init",
        "get", "set", "parse", "load", "save",
    ]

    def fts5_run():
        for q in queries:
            db.search_symbols(q, limit=5)

    fts5 = timed(fts5_run, runs=runs)

    def sym_run():
        for q in queries[:5]:
            find_symbols(q, root, limit=5)

    sym = timed(sym_run, runs=runs)

    callable_syms = db.search_by_name("", limit=5) or [{"id": "x"}]

    def caller_run():
        for s in callable_syms[:3]:
            db.get_callers(s.get("id", "x"), max_depth=1)

    callers = timed(caller_run, runs=runs)

    return {
        "project": root.name,
        "symbols": stats["symbol_count"],
        "edges": stats["edge_count"],
        "files": stats["file_count"],
        "db_mb": stats["db_size_mb"],
        "build_ms": build["median_ms"],
        "fts5_ms": round(fts5["median_ms"] / len(queries), 3),
        "lookup_ms": sym["median_ms"],
        "callers_ms": callers["median_ms"],
    }


# ── v0.1 Benchmarks ──────────────────────────────────────────────

def bench_v0_1(root: Path, runs: int) -> Dict[str, Any]:
    """Run v0.1-specific benchmarks."""
    sys.path.insert(0, str(_PROJECT_SELF))
    from context_engine.primitives import (
        build_registry, build_execution_dag, compute_parallelism_ratio,
        get_primitive,
    )
    from context_engine.invalidation import (
        classify_change, get_weighted_decay, _is_high_risk_module,
        compute_semantic_confidence, should_recompress, extract_signatures,
    )
    from context_engine import compressor

    reg = build_registry()
    all_names = list(reg.keys())

    # ── Registry + DAG ──
    def dag_build():
        build_execution_dag(all_names)

    dag = timed(dag_build, runs=runs)

    ratio = compute_parallelism_ratio(all_names)

    pure = sum(1 for p in reg.values() if p.contract.is_pure)
    mutative = sum(1 for p in reg.values() if p.contract.purity == "mutative")
    psafe = sum(1 for p in reg.values() if p.contract.parallel_safe)

    # ── Optimizer ──
    from context_engine.optimizer import optimize_dag

    test_primitives = [
        "graph.analyze_target",
        "graph.trace_callers",
        "graph.analyze_target",  # duplicate
        "memory.recall",
        "verify.architecture",
        "context.summarize",
    ]

    def opt_run():
        optimize_dag(test_primitives, {"target": "test"}, {})

    opt = timed(opt_run, runs=runs)
    opt_result = optimize_dag(test_primitives, {"target": "test"}, {})

    # ── Signature Extraction ──
    py_files = list(root.rglob("context_engine/*.py"))[:30]
    if not py_files:
        py_files = list(root.rglob("*.py"))[:30]

    def sig_run():
        total = 0
        for f in py_files:
            sigs = extract_signatures(f)
            total += len(sigs)
        return total

    sig = timed(sig_run, runs=runs)
    total_sigs = sig_run() if py_files else 0

    # ── classify_change ──
    test_file = py_files[0] if py_files else None

    def classify_run():
        if test_file:
            classify_change(test_file)

    classify = timed(classify_run, runs=runs) if test_file else {"median_ms": 0}

    # ── Weighted Decay ──
    def decay_run():
        for ct in ["body_only_change", "signature_change", "architectural_hotspot"]:
            get_weighted_decay(ct)

    decay = timed(decay_run, runs=runs)

    # ── High-Risk Detection ──
    risk_paths = [
        "src/auth/login.py", "app/security/crypto.py",
        "src/utils/helpers.py", "tests/test_main.py",
    ]

    def risk_run():
        for p in risk_paths:
            _is_high_risk_module(p)

    risk = timed(risk_run, runs=runs)

    # ── Semantic Confidence ──
    def semconf_run():
        compute_semantic_confidence(10, 3)
        compute_semantic_confidence(50, 10, "src/auth/login.py")
        compute_semantic_confidence(5, 1)

    semconf = timed(semconf_run, runs=runs)

    # ── Compression Confidence ──
    def compconf_run():
        compressor.reset_compression_confidence(root)
        compressor.apply_compression_decay("body_only_change", change_count=3,
                                            project_root=root)
        compressor.apply_compression_decay("signature_change", change_count=1,
                                            project_root=root)

    compconf = timed(compconf_run, runs=runs)

    # ── Threshold ──
    def threshold_run():
        should_recompress(0.59)
        should_recompress(0.60)
        should_recompress(0.80)

    threshold = timed(threshold_run, runs=runs)

    return {
        "project": root.name,
        # Typed capabilities
        "typed_pure": pure,
        "typed_mutative": mutative,
        "typed_parallel_safe": psafe,
        "typed_total": len(reg),
        # DAG
        "dag_build_ms": dag["median_ms"],
        "dag_parallelism_ratio": ratio,
        # Optimizer
        "opt_time_ms": opt["median_ms"],
        "opt_original": opt_result.original_count,
        "opt_optimized": opt_result.optimized_count,
        "opt_ratio": opt_result.optimization_ratio,
        "opt_passes": ",".join(opt_result.applied_passes),
        # Signature extraction
        "sig_total": total_sigs,
        "sig_files": len(py_files),
        "sig_time_ms": sig["median_ms"],
        # classify_change
        "classify_ms": classify["median_ms"],
        # Weighted decay
        "decay_lookup_ms": decay["median_ms"],
        # High-risk detection
        "risk_detect_ms": risk["median_ms"],
        # Semantic confidence
        "semconf_ms": semconf["median_ms"],
        # Compression confidence
        "compconf_ms": compconf["median_ms"],
        # Threshold
        "threshold_ms": threshold["median_ms"],
    }


# ── Display ──────────────────────────────────────────────────────

def print_classic_table(results: List[Dict[str, Any]]):
    all_build = [r["build_ms"] for r in results]
    all_fts5 = [r["fts5_ms"] for r in results]
    all_lookup = [r["lookup_ms"] for r in results]
    all_sym = [r["symbols"] for r in results]
    all_db = [r["db_mb"] for r in results]

    print(f"\n{'─'*70}")
    print(f"{'Classic Metrics':^70}")
    print(f"{'─'*70}")
    print(f"{'Metric':<30} {'Min':>8} {'Median':>8} {'Max':>8}")
    print(f"{'─'*30} {'─'*8} {'─'*8} {'─'*8}")
    print(f"{'Cache build (ms)':<30} {min(all_build):>8.1f} {median(all_build):>8.1f} {max(all_build):>8.1f}")
    print(f"{'FTS5 search (ms/q)':<30} {min(all_fts5):>8.3f} {median(all_fts5):>8.3f} {max(all_fts5):>8.3f}")
    print(f"{'JSON lookup (ms/q)':<30} {min(all_lookup):>8.1f} {median(all_lookup):>8.1f} {max(all_lookup):>8.1f}")
    print(f"{'Symbols':<30} {min(all_sym):>8} {int(median(all_sym)):>8} {max(all_sym):>8}")
    print(f"{'DB size (MB)':<30} {min(all_db):>8.2f} {median(all_db):>8.2f} {max(all_db):>8.2f}")

    print(f"\n{'Project':<28} {'Sym':>6} {'Build':>7} {'FTS5':>7} {'Lookup':>7} {'DB':>6}")
    print(f"{'─'*28} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*6}")
    for r in results:
        print(f"{r['project']:<28} {r['symbols']:>6} {r['build_ms']:>6.0f}ms "
              f"{r['fts5_ms']:>6.2f}ms {r['lookup_ms']:>6.0f}ms {r['db_mb']:>5.1f}M")


def print_v0_1_table(results: List[Dict[str, Any]]):
    if not results:
        return
    r = results[0]  # Single project mode for v0.1

    print(f"\n{'─'*70}")
    print(f"{'v0.1 Kernel Metrics':^70}")
    print(f"{'─'*70}")

    # Typed capabilities
    print(f"\n{'Typed Execution Capabilities':─^50}")
    print(f"  Pure: {r['typed_pure']}/{r['typed_total']}  "
          f"Mutative: {r['typed_mutative']}/{r['typed_total']}  "
          f"Parallel-safe: {r['typed_parallel_safe']}/{r['typed_total']}")

    # DAG + Optimizer
    print(f"\n{'DAG + Optimizer':─^50}")
    print(f"  DAG build: {r['dag_build_ms']:.3f}ms  "
          f"Parallelism: {r['dag_parallelism_ratio']:.0%}")
    print(f"  Optimize: {r['opt_time_ms']:.3f}ms  "
          f"{r['opt_original']}→{r['opt_optimized']} primitives "
          f"(ratio: {r['opt_ratio']:.0%})")
    print(f"  Passes: {r['opt_passes']}")

    # Semantic Invalidation
    print(f"\n{'Semantic Invalidation':─^50}")
    print(f"  Signature extraction: {r['sig_time_ms']:.2f}ms "
          f"({r['sig_files']} files, {r['sig_total']} sigs)")
    print(f"  classify_change: {r['classify_ms']:.3f}ms/file")
    print(f"  Weighted decay lookup: {r['decay_lookup_ms']:.3f}ms")
    print(f"  High-risk detection: {r['risk_detect_ms']:.3f}ms")
    print(f"  Semantic confidence: {r['semconf_ms']:.3f}ms")
    print(f"  Threshold check: {r['threshold_ms']:.3f}ms")

    # Compression
    print(f"\n{'Compression Confidence':─^50}")
    print(f"  Decay apply: {r['compconf_ms']:.3f}ms")


# ── Main ─────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description="aihelper benchmarks (v0.1)")
    p.add_argument("--project-root", default=None, help="Project to benchmark")
    p.add_argument("--runs", type=int, default=4, help="Runs per metric")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--quick", action="store_true", help="v0.1-only fast mode")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()
    runs = args.runs

    if args.project_root:
        roots = [Path(args.project_root).resolve()]
    else:
        roots = discover_projects()
        if not roots:
            print("No projects found under ~/github")
            return 1

    print(f"aihelper v0.1 Benchmarks — {len(roots)} project(s), {runs} runs/ea")

    # Classic benchmarks
    if not args.quick:
        print("\n[1/2] Running classic benchmarks...")
        classic_results = []
        for root in roots:
            print(f"  {root.name}...", end=" ", flush=True)
            try:
                r = bench_classic(root, runs)
                classic_results.append(r)
                print(f"OK ({r['symbols']} sym, {r['build_ms']:.0f}ms)")
            except Exception as e:
                print(f"SKIP ({e})")
        if classic_results:
            print_classic_table(classic_results)

    # v0.1 benchmarks
    print("\n[2/2] Running v0.1 kernel benchmarks...")
    v01_results = []
    for root in roots:
        print(f"  {root.name}...", end=" ", flush=True)
        try:
            r = bench_v0_1(root, runs)
            v01_results.append(r)
            print(f"OK ({r['typed_pure']} pure, {r['sig_total']} sigs)")
        except Exception as e:
            print(f"SKIP ({e})")
    if v01_results:
        print_v0_1_table(v01_results)

    if args.json:
        output = {}
        if not args.quick:
            output["classic"] = classic_results if 'classic_results' in dir() else []
        output["v0.1"] = v01_results
        print("\n" + json.dumps(output, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
