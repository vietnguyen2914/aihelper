#!/usr/bin/env python3
"""benchmark.py — aihelper v0.0.7 local benchmarks (4 runs, median reported)."""
from __future__ import annotations
import json, statistics, sys, time
from pathlib import Path
from typing import Any, Dict, List

GITHUB_ROOT = Path.home() / "github"
WARMUP = 1


def median(vals: List[float]) -> float:
    return statistics.median(vals) if vals else 0.0


def timed(func, runs=4, warmup=1) -> Dict[str, float]:
    for _ in range(warmup):
        func()
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        func()
        times.append((time.perf_counter() - t0) * 1000)
    return {"min_ms": round(min(times), 2), "max_ms": round(max(times), 2),
            "median_ms": round(median(times), 2), "runs": runs}


def discover_projects() -> List[Path]:
    roots = []
    if GITHUB_ROOT.exists():
        for d in sorted(GITHUB_ROOT.iterdir()):
            if d.is_dir() and (d / ".git").exists():
                roots.append(d)
    return roots


def bench_project(root: Path, runs: int) -> Dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from context_engine.cache import build_cache, clean_cache
    from context_engine.graph_db import get_db
    from context_engine.symbols import find_symbols

    print(f"  {root.name}...", end=" ", flush=True)

    # Cache build
    clean_cache(root)
    build = timed(lambda: build_cache(root), runs=runs)

    # DB stats
    db = get_db(root)
    stats = db.get_stats()
    json_sz = sum((root / ".ai-cache" / "aihelper").glob("*.json")).stat().st_size if False else 0

    # FTS5
    queries = ["main", "build", "cache", "handle", "init", "get", "set", "parse", "load", "save"]
    def fts5_run():
        for q in queries:
            db.search_symbols(q, limit=5)

    fts5 = timed(fts5_run, runs=runs)

    # Symbol lookup (JSON fallback path)
    def sym_run():
        for q in queries[:5]:
            find_symbols(q, root, limit=5)

    sym = timed(sym_run, runs=runs)

    # Callers
    callable_syms = db.search_by_name("", limit=5) or [{"id": "x"}]
    def caller_run():
        for s in callable_syms[:3]:
            db.get_callers(s.get("id", "x"), max_depth=1)

    callers = timed(caller_run, runs=runs)

    r = {
        "project": root.name,
        "symbols": stats["symbol_count"], "edges": stats["edge_count"],
        "files": stats["file_count"], "db_mb": stats["db_size_mb"],
        "build_ms": build["median_ms"],
        "fts5_ms": round(fts5["median_ms"] / len(queries), 3) if len(queries) else 0,
        "lookup_ms": sym["median_ms"],
        "callers_ms": callers["median_ms"],
    }
    print(f"OK ({r['symbols']} sym, {r['db_mb']}MB, {r['build_ms']:.0f}ms build)")
    return r


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--project-root", default=None)
    p.add_argument("--runs", type=int, default=4)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    runs = args.runs

    if args.project_root:
        roots = [Path(args.project_root).resolve()]
    else:
        roots = discover_projects()
        if not roots:
            print("No projects found under ~/github"); return 1

    print(f"aihelper v0.0.7 Benchmarks — {len(roots)} projects, {runs} runs/ea\n")
    results = [bench_project(r, runs) for r in roots]
    success = [r for r in results if "error" not in r]

    if not success:
        print("No successful benchmarks."); return 1

    all_build = [r["build_ms"] for r in success]
    all_fts5 = [r["fts5_ms"] for r in success]
    all_lookup = [r["lookup_ms"] for r in success]
    all_sym = [r["symbols"] for r in success]
    all_db = [r["db_mb"] for r in success]

    print(f"\n{'='*70}")
    print(f"{'Metric':<30} {'Min':>8} {'Median':>8} {'Max':>8}")
    print(f"{'-'*30} {'-'*8} {'-'*8} {'-'*8}")
    print(f"{'Cache build (ms)':<30} {min(all_build):>8.1f} {median(all_build):>8.1f} {max(all_build):>8.1f}")
    print(f"{'FTS5 search (ms/q)':<30} {min(all_fts5):>8.3f} {median(all_fts5):>8.3f} {max(all_fts5):>8.3f}")
    print(f"{'JSON lookup (ms/q)':<30} {min(all_lookup):>8.1f} {median(all_lookup):>8.1f} {max(all_lookup):>8.1f}")
    print(f"{'Symbols':<30} {min(all_sym):>8} {int(median(all_sym)):>8} {max(all_sym):>8}")
    print(f"{'DB size (MB)':<30} {min(all_db):>8.2f} {median(all_db):>8.2f} {max(all_db):>8.2f}")

    print(f"\n{'Project':<28} {'Sym':>6} {'Build':>7} {'FTS5':>7} {'Lookup':>7} {'DB':>6}")
    print(f"{'-'*28} {'-'*6} {'-'*7} {'-'*7} {'-'*7} {'-'*6}")
    for r in success:
        print(f"{r['project']:<28} {r['symbols']:>6} {r['build_ms']:>6.0f}ms {r['fts5_ms']:>6.2f}ms {r['lookup_ms']:>6.0f}ms {r['db_mb']:>5.1f}M")

    if args.json:
        print("\n" + json.dumps({"summary": {"build_median": round(median(all_build), 1),
            "fts5_per_query_median_ms": round(median(all_fts5), 3),
            "projects": results}}, indent=2))

if __name__ == "__main__":
    raise SystemExit(main())
