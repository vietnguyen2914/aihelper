"""
Telemetry-Driven Benchmark — generate benchmark reports from actual runtime data.

Every metric MUST come from real telemetry (SQLite queries), NEVER estimated
or hallucinated. If data is missing, show "N/A" — never fabricate numbers.

Data sources:
  - Graph DB (SQLite): symbol_count, file_count, edge_count
  - Invalidation log: invalidation_stats
  - Cache manifest: cache_stats
  - Intelligence DB (knowledge_decisions / architectural_decisions): workflow traces
  - Telemetry singleton: daemon runtime metrics
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


# ── Main Benchmark Generation ──────────────────────────────────────

def generate_benchmark(project_root: Path) -> Dict[str, Any]:
    """Generate a telemetry-driven benchmark report.

    Every metric is sourced from actual stored telemetry.
    Returns a dict with sections: system_state, runtime_metrics,
    optimization_metrics, invalidation_metrics, token_efficiency.
    """
    project_root = project_root.resolve()
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── System State ──────────────────────────────────────────────
    system_state = _collect_system_state(project_root)

    # ── Runtime Metrics ───────────────────────────────────────────
    runtime = _collect_runtime_metrics()

    # ── Optimization Metrics (from workflow traces) ──────────────
    optimization = _collect_optimization_metrics(project_root)

    # ── Invalidation Metrics ─────────────────────────────────────
    invalidation = _collect_invalidation_metrics()

    # ── Token Efficiency ─────────────────────────────────────────
    token_efficiency = _compute_token_efficiency(project_root)

    # ── Cache Performance ────────────────────────────────────────
    cache_perf = _collect_cache_performance(project_root)

    return {
        "generated_at": now_iso,
        "project_root": str(project_root),
        "system_state": system_state,
        "runtime_metrics": runtime,
        "optimization_metrics": optimization,
        "invalidation_metrics": invalidation,
        "token_efficiency": token_efficiency,
        "cache_performance": cache_perf,
    }


# ── Section Collectors ────────────────────────────────────────────

def _collect_system_state(project_root: Path) -> Dict[str, Any]:
    """Collect graph DB state: symbol count, file count, edge stats."""
    try:
        from .graph_db import get_db
        db = get_db(project_root)
        stats = db.get_stats()
        return {
            "symbol_count": stats.get("symbol_count", 0),
            "file_count": stats.get("file_count", 0),
            "edge_count": stats.get("edge_count", 0),
            "db_size_mb": stats.get("db_size_mb", 0),
            "nodes_by_kind": stats.get("nodes_by_kind", {}),
            "files_by_language": stats.get("files_by_language", {}),
            "edges_by_kind": stats.get("edges_by_kind", {}),
            "journal_mode": stats.get("journal_mode", "N/A"),
        }
    except Exception:
        return _na_system_state()


def _na_system_state() -> Dict[str, Any]:
    return {
        "symbol_count": "N/A",
        "file_count": "N/A",
        "edge_count": "N/A",
        "db_size_mb": "N/A",
        "nodes_by_kind": {},
        "files_by_language": {},
        "edges_by_kind": {},
        "journal_mode": "N/A",
    }


def _collect_runtime_metrics() -> Dict[str, Any]:
    """Collect daemon runtime metrics from telemetry singleton."""
    try:
        from .telemetry import get_telemetry
        snap = get_telemetry().get_snapshot()
        return {
            "uptime_seconds": snap.get("uptime_seconds", "N/A"),
            "uptime_human": snap.get("uptime_human", "N/A"),
            "total_requests": snap.get("requests", {}).get("total", 0),
            "request_rate_per_second": snap.get("requests", {}).get("rate_per_second", 0),
            "request_breakdown": snap.get("requests", {}).get("breakdown", {}),
            "cache_hits": snap.get("cache", {}).get("hits", 0),
            "cache_misses": snap.get("cache", {}).get("misses", 0),
            "cache_hit_rate": snap.get("cache", {}).get("hit_rate", 0),
            "cache_builds": snap.get("cache", {}).get("builds", 0),
            "latency_ms": snap.get("latency_ms", {}),
            "errors": snap.get("errors", {}),
            "warmup_runs": snap.get("warmup_runs", 0),
            "connections": snap.get("connections", 0),
        }
    except Exception:
        return {
            "uptime_seconds": "N/A",
            "uptime_human": "N/A",
            "total_requests": "N/A",
            "request_rate_per_second": "N/A",
            "request_breakdown": {},
            "cache_hits": "N/A",
            "cache_misses": "N/A",
            "cache_hit_rate": "N/A",
            "cache_builds": "N/A",
            "latency_ms": {},
            "errors": {},
            "warmup_runs": "N/A",
            "connections": "N/A",
        }


def _collect_optimization_metrics(project_root: Path) -> Dict[str, Any]:
    """Collect optimization metrics from stored workflow traces.

    Queries the intelligence DB for workflow trace records
    (inserted by workflow_engine._record_observability) and
    aggregates optimization pass stats.
    """
    traces = _load_workflow_traces(project_root)

    if not traces:
        return {
            "total_workflow_runs": 0,
            "optimization_passes_total": 0,
            "cache_hits_from_traces": 0,
            "folded_nodes_total": 0,
            "avg_optimization_ratio": "N/A",
            "avg_speedup": "N/A",
            "by_workflow": {},
        }

    total_runs = len(traces)
    optimization_passes: Dict[str, int] = {}
    total_cache_hits = 0
    total_folded = 0
    speedups: List[float] = []
    ratios: List[float] = []
    by_workflow: Dict[str, Dict[str, Any]] = {}

    for trace in traces:
        wf_name = trace.get("workflow", "unknown")
        opt = trace.get("optimization", {})

        passes = opt.get("applied_passes", [])
        for p in passes:
            optimization_passes[p] = optimization_passes.get(p, 0) + 1

        cache_hits = len(opt.get("cache_hits", []))
        folded = len(opt.get("folded_nodes", []))
        total_cache_hits += cache_hits
        total_folded += folded

        speedup = opt.get("estimated_speedup", 1.0)
        ratio = opt.get("optimization_ratio", 1.0)
        if isinstance(speedup, (int, float)):
            speedups.append(float(speedup))
        if isinstance(ratio, (int, float)):
            ratios.append(float(ratio))

        if wf_name not in by_workflow:
            by_workflow[wf_name] = {"runs": 0, "cache_hits": 0, "folded_nodes": 0, "speedups": []}
        by_workflow[wf_name]["runs"] += 1
        by_workflow[wf_name]["cache_hits"] += cache_hits
        by_workflow[wf_name]["folded_nodes"] += folded
        if isinstance(speedup, (int, float)):
            by_workflow[wf_name]["speedups"].append(float(speedup))

    # Clean up by_workflow — average the speedups
    for wf, data in by_workflow.items():
        data["avg_speedup"] = round(sum(data["speedups"]) / max(len(data["speedups"]), 1), 2)
        del data["speedups"]

    return {
        "total_workflow_runs": total_runs,
        "optimization_passes_total": sum(optimization_passes.values()),
        "optimization_passes_breakdown": optimization_passes,
        "cache_hits_from_traces": total_cache_hits,
        "folded_nodes_total": total_folded,
        "avg_optimization_ratio": round(sum(ratios) / max(len(ratios), 1), 2) if ratios else "N/A",
        "avg_speedup": round(sum(speedups) / max(len(speedups), 1), 2) if speedups else "N/A",
        "by_workflow": by_workflow,
    }


def _load_workflow_traces(project_root: Path) -> List[Dict[str, Any]]:
    """Load workflow trace records from the intelligence DB.

    Traces are stored in knowledge_decisions (or architectural_decisions as fallback)
    with id prefix 'wf_trace_'. Each record's 'reason' column contains a JSON blob
    with the workflow result including optimization metadata.
    """
    traces: List[Dict[str, Any]] = []
    try:
        from .intelligence.storage import get_db as get_intel_db
        db = get_intel_db(project_root)

        # Try knowledge_decisions first (where workflow_engine writes),
        # fall back to architectural_decisions
        table = None
        for candidate in ("knowledge_decisions", "architectural_decisions"):
            try:
                db.execute(f"SELECT 1 FROM {candidate} LIMIT 1")
                table = candidate
                break
            except Exception:
                continue

        if table is None:
            return traces

        rows = db.execute(
            f"SELECT id, choice, reason, created_at FROM {table} "
            "WHERE id LIKE 'wf_trace_%' ORDER BY created_at DESC LIMIT 500"
        ).fetchall()

        for row in rows:
            try:
                record = json.loads(row["reason"])
                # Enrich with the workflow name from 'choice' column
                if isinstance(record, dict):
                    record.setdefault("workflow", row["choice"])
                    record.setdefault("trace_id", row["id"])
                    record.setdefault("timestamp", row["created_at"])
                traces.append(record)
            except (json.JSONDecodeError, TypeError):
                continue

    except Exception:
        pass

    return traces


def _collect_invalidation_metrics() -> Dict[str, Any]:
    """Collect invalidation statistics from the invalidation log."""
    try:
        from .invalidation import get_invalidation_stats
        stats = get_invalidation_stats()
        return {
            "total_entries": stats.get("total", 0),
            "by_reason": stats.get("by_reason", {}),
            "by_level": stats.get("by_level", {}),
            "oldest": stats.get("oldest", "N/A"),
            "newest": stats.get("newest", "N/A"),
        }
    except Exception:
        return {
            "total_entries": "N/A",
            "by_reason": {},
            "by_level": {},
            "oldest": "N/A",
            "newest": "N/A",
        }


def _compute_token_efficiency(project_root: Path) -> Dict[str, Any]:
    """Compute token efficiency metrics from workflow traces.

    Measures Ollama (local) vs Frontier (cloud) token usage ratios.
    All numbers sourced from actual workflow trace telemetry.
    """
    traces = _load_workflow_traces(project_root)

    if not traces:
        return {
            "total_workflows_analyzed": 0,
            "total_tokens_all": "N/A",
            "local_model_tokens": "N/A",
            "frontier_tokens": "N/A",
            "deterministic_tokens": "N/A",
            "local_frontier_ratio": "N/A",
            "avg_tokens_per_workflow": "N/A",
            "by_workflow": {},
        }

    total_all = 0
    total_local = 0
    total_frontier = 0
    total_deterministic = 0
    by_workflow: Dict[str, Dict[str, Any]] = {}

    for trace in traces:
        wf_name = trace.get("workflow", "unknown")
        breakdown = trace.get("token_breakdown", {})

        wf_total = trace.get("total_tokens", 0)
        wf_local = breakdown.get("local_model", 0)
        wf_frontier = breakdown.get("frontier", 0)
        wf_det = breakdown.get("deterministic", 0)

        total_all += wf_total
        total_local += wf_local
        total_frontier += wf_frontier
        total_deterministic += wf_det

        if wf_name not in by_workflow:
            by_workflow[wf_name] = {"runs": 0, "tokens": 0, "local": 0, "frontier": 0}
        by_workflow[wf_name]["runs"] += 1
        by_workflow[wf_name]["tokens"] += wf_total
        by_workflow[wf_name]["local"] += wf_local
        by_workflow[wf_name]["frontier"] += wf_frontier

    run_count = len(traces)
    ratio = round(total_local / max(total_frontier, 1), 2)

    return {
        "total_workflows_analyzed": run_count,
        "total_tokens_all": total_all,
        "local_model_tokens": total_local,
        "frontier_tokens": total_frontier,
        "deterministic_tokens": total_deterministic,
        "local_frontier_ratio": ratio,
        "avg_tokens_per_workflow": round(total_all / max(run_count, 1), 2),
        "by_workflow": by_workflow,
    }


def _collect_cache_performance(project_root: Path) -> Dict[str, Any]:
    """Collect cache performance metrics from the cache manifest."""
    try:
        from .cache import cache_status
        status = cache_status(project_root)
        manifest = status.get("manifest", {})

        return {
            "cache_exists": status.get("exists", False),
            "cache_fresh": status.get("fresh", False),
            "cache_version": manifest.get("version", "N/A"),
            "cached_symbol_count": manifest.get("symbol_count", "N/A"),
            "cached_file_count": manifest.get("file_count", "N/A"),
            "built_at": manifest.get("built_at", "N/A"),
            "cache_files_present": status.get("files", {}),
        }
    except Exception:
        return {
            "cache_exists": "N/A",
            "cache_fresh": "N/A",
            "cache_version": "N/A",
            "cached_symbol_count": "N/A",
            "cached_file_count": "N/A",
            "built_at": "N/A",
            "cache_files_present": {},
        }


# ── Markdown Formatter ────────────────────────────────────────────

def format_benchmark_markdown(benchmark: Dict[str, Any]) -> str:
    """Render a benchmark dict as a clean markdown report.

    Only uses actual numbers from telemetry. If data is missing,
    renders 'N/A' — never estimates.
    """
    lines: List[str] = []
    _h = lines.append

    _h("# AIHelper Benchmark Report")
    _h(f"**Generated:** {benchmark.get('generated_at', 'N/A')}")
    _h(f"**Project:** {benchmark.get('project_root', 'N/A')}")
    _h("")

    # ── System State ──────────────────────────────────────────────
    ss = benchmark.get("system_state", {})
    _h("## System State")
    _h("")
    _h(f"| Metric | Value |")
    _h(f"|--------|-------|")
    _h(f"| Symbols indexed | {ss.get('symbol_count', 'N/A')} |")
    _h(f"| Files indexed | {ss.get('file_count', 'N/A')} |")
    _h(f"| Graph edges | {ss.get('edge_count', 'N/A')} |")
    _h(f"| DB size | {ss.get('db_size_mb', 'N/A')} MB |")
    _h(f"| Journal mode | {ss.get('journal_mode', 'N/A')} |")
    _h("")

    nodes = ss.get("nodes_by_kind", {})
    if nodes:
        _h("### Nodes by Kind")
        _h("")
        for kind, count in sorted(nodes.items()):
            _h(f"- **{kind}**: {count}")
        _h("")

    langs = ss.get("files_by_language", {})
    if langs:
        _h("### Files by Language")
        _h("")
        for lang, count in sorted(langs.items()):
            _h(f"- **{lang}**: {count}")
        _h("")

    # ── Cache Performance ────────────────────────────────────────
    cp = benchmark.get("cache_performance", {})
    _h("## Cache Performance")
    _h("")
    _h(f"| Metric | Value |")
    _h(f"|--------|-------|")
    _h(f"| Cache exists | {cp.get('cache_exists', 'N/A')} |")
    _h(f"| Cache fresh | {cp.get('cache_fresh', 'N/A')} |")
    _h(f"| Cache version | {cp.get('cache_version', 'N/A')} |")
    _h(f"| Cached symbols | {cp.get('cached_symbol_count', 'N/A')} |")
    _h(f"| Cached files | {cp.get('cached_file_count', 'N/A')} |")
    _h(f"| Built at | {cp.get('built_at', 'N/A')} |")
    _h("")

    # ── Token Efficiency ─────────────────────────────────────────
    te = benchmark.get("token_efficiency", {})
    _h("## Token Efficiency (Ollama vs Frontier)")
    _h("")
    _h(f"| Metric | Value |")
    _h(f"|--------|-------|")
    _h(f"| Workflows analyzed | {te.get('total_workflows_analyzed', 'N/A')} |")
    _h(f"| Total tokens (all) | {te.get('total_tokens_all', 'N/A')} |")
    _h(f"| Local model tokens | {te.get('local_model_tokens', 'N/A')} |")
    _h(f"| Frontier tokens | {te.get('frontier_tokens', 'N/A')} |")
    _h(f"| Deterministic tokens | {te.get('deterministic_tokens', 'N/A')} |")
    _h(f"| Local : Frontier ratio | {te.get('local_frontier_ratio', 'N/A')} |")
    _h(f"| Avg tokens / workflow | {te.get('avg_tokens_per_workflow', 'N/A')} |")
    _h("")

    by_wf = te.get("by_workflow", {})
    if by_wf:
        _h("### Per-Workflow Token Breakdown")
        _h("")
        for wf, data in sorted(by_wf.items()):
            _h(f"- **{wf}**: {data.get('runs', 0)} runs, "
               f"{data.get('tokens', 0)} total tokens "
               f"(local: {data.get('local', 0)}, frontier: {data.get('frontier', 0)})")
        _h("")

    # ── Invalidation Health ──────────────────────────────────────
    im = benchmark.get("invalidation_metrics", {})
    _h("## Invalidation Health")
    _h("")
    _h(f"| Metric | Value |")
    _h(f"|--------|-------|")
    _h(f"| Total entries | {im.get('total_entries', 'N/A')} |")
    _h(f"| Oldest entry | {im.get('oldest', 'N/A')} |")
    _h(f"| Newest entry | {im.get('newest', 'N/A')} |")
    _h("")

    by_reason = im.get("by_reason", {})
    if by_reason:
        _h("### By Reason")
        _h("")
        for reason, count in sorted(by_reason.items()):
            _h(f"- **{reason}**: {count}")
        _h("")

    by_level = im.get("by_level", {})
    if by_level:
        _h("### By Level")
        _h("")
        for level, count in sorted(by_level.items()):
            _h(f"- **{level}**: {count}")
        _h("")

    # ── Optimization Impact ──────────────────────────────────────
    om = benchmark.get("optimization_metrics", {})
    _h("## Optimization Impact")
    _h("")
    _h(f"| Metric | Value |")
    _h(f"|--------|-------|")
    _h(f"| Total workflow runs | {om.get('total_workflow_runs', 'N/A')} |")
    _h(f"| Optimization passes applied | {om.get('optimization_passes_total', 'N/A')} |")
    _h(f"| Cache hits (from traces) | {om.get('cache_hits_from_traces', 'N/A')} |")
    _h(f"| Folded nodes | {om.get('folded_nodes_total', 'N/A')} |")
    _h(f"| Avg optimization ratio | {om.get('avg_optimization_ratio', 'N/A')} |")
    _h(f"| Avg estimated speedup | {om.get('avg_speedup', 'N/A')}x |")
    _h("")

    passes = om.get("optimization_passes_breakdown", {})
    if passes:
        _h("### Optimization Passes Breakdown")
        _h("")
        for p, count in sorted(passes.items()):
            _h(f"- **{p}**: {count}")
        _h("")

    by_wf_opt = om.get("by_workflow", {})
    if by_wf_opt:
        _h("### Per-Workflow Optimization")
        _h("")
        for wf, data in sorted(by_wf_opt.items()):
            _h(f"- **{wf}**: {data.get('runs', 0)} runs, "
               f"{data.get('cache_hits', 0)} cache hits, "
               f"{data.get('folded_nodes', 0)} folded nodes, "
               f"avg speedup {data.get('avg_speedup', 'N/A')}x")
        _h("")

    # ── Runtime Metrics ──────────────────────────────────────────
    rm = benchmark.get("runtime_metrics", {})
    _h("## Runtime Metrics")
    _h("")
    _h(f"| Metric | Value |")
    _h(f"|--------|-------|")
    _h(f"| Uptime | {rm.get('uptime_human', 'N/A')} |")
    _h(f"| Total requests | {rm.get('total_requests', 'N/A')} |")
    _h(f"| Request rate | {rm.get('request_rate_per_second', 'N/A')}/s |")
    _h(f"| Cache hit rate (runtime) | {rm.get('cache_hit_rate', 'N/A')} |")
    _h(f"| Cache builds | {rm.get('cache_builds', 'N/A')} |")
    _h(f"| Warmup runs | {rm.get('warmup_runs', 'N/A')} |")
    _h(f"| Connections | {rm.get('connections', 'N/A')} |")
    _h("")

    errors = rm.get("errors", {})
    if errors:
        _h("### Runtime Errors")
        _h("")
        for err, count in sorted(errors.items()):
            _h(f"- **{err}**: {count}")
        _h("")

    return "\n".join(lines)


# ── Benchmark Comparison ──────────────────────────────────────────

def compare_benchmarks(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two benchmark snapshots and return per-metric deltas.

    Each metric shows before, after, and delta. String or non-numeric
    metrics are compared by identity.
    """
    sections = [
        "system_state",
        "runtime_metrics",
        "optimization_metrics",
        "invalidation_metrics",
        "token_efficiency",
        "cache_performance",
    ]

    result: Dict[str, Any] = {
        "before_time": before.get("generated_at", "N/A"),
        "after_time": after.get("generated_at", "N/A"),
    }

    for section in sections:
        before_sec = before.get(section, {})
        after_sec = after.get(section, {})
        deltas: Dict[str, Any] = {}

        all_keys = set(before_sec.keys()) | set(after_sec.keys())
        for key in sorted(all_keys):
            b_val = before_sec.get(key, "N/A")
            a_val = after_sec.get(key, "N/A")

            if isinstance(b_val, (int, float)) and isinstance(a_val, (int, float)):
                deltas[key] = {
                    "before": b_val,
                    "after": a_val,
                    "delta": a_val - b_val,
                    "delta_pct": round(((a_val - b_val) / max(abs(b_val), 1)) * 100, 1) if b_val != 0 else "N/A",
                }
            elif isinstance(b_val, dict) and isinstance(a_val, dict):
                # For nested dicts, compute key-level deltas
                nested_deltas: Dict[str, Any] = {}
                nested_keys = set(b_val.keys()) | set(a_val.keys())
                for nk in sorted(nested_keys):
                    nb = b_val.get(nk, 0)
                    na = a_val.get(nk, 0)
                    if isinstance(nb, (int, float)) and isinstance(na, (int, float)):
                        nested_deltas[nk] = {"before": nb, "after": na, "delta": na - nb}
                    else:
                        nested_deltas[nk] = {"before": str(nb), "after": str(na), "changed": nb != na}
                deltas[key] = nested_deltas
            else:
                deltas[key] = {
                    "before": str(b_val),
                    "after": str(a_val),
                    "changed": b_val != a_val,
                }

        result[section] = deltas

    return result


# ── Daemon Handlers ───────────────────────────────────────────────

def _resolve_project(params: Dict[str, Any]) -> Path:
    """Resolve project_root from params, defaulting to CWD."""
    import os
    root = params.get("project_root") or os.getcwd()
    return Path(root).resolve()


def handle_benchmark(params: Dict[str, Any]) -> Dict[str, Any]:
    """Daemon handler: return benchmark as structured JSON."""
    project_root = _resolve_project(params)
    benchmark = generate_benchmark(project_root)
    return {
        "ok": True,
        "benchmark": benchmark,
    }


def handle_benchmark_export(params: Dict[str, Any]) -> Dict[str, Any]:
    """Daemon handler: return benchmark as a markdown string."""
    project_root = _resolve_project(params)
    benchmark = generate_benchmark(project_root)
    markdown = format_benchmark_markdown(benchmark)
    return {
        "ok": True,
        "markdown": markdown,
        "benchmark": benchmark,  # Also include raw data for programmatic use
    }
