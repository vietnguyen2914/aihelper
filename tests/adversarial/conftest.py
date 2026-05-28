"""conftest.py for adversarial test suite."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# ── Ensure the project root is on sys.path ────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def pytest_addoption(parser):
    parser.addoption("--report", action="store_true", default=False,
                     help="Print full recovery report at end of test session")


def pytest_sessionfinish(session, exitstatus):
    """Generate replay determinism report after all tests complete."""
    report_path = _PROJECT_ROOT / "tests" / "adversarial" / "replay_report.json"
    report = {
        "suite": "Deterministic Replay Validation",
        "project": str(_PROJECT_ROOT),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scenarios": {
            "test_single_primitive_replay": {
                "description": "Single primitive (graph.analyze_target) × 20 runs, fresh engine each run",
                "runs": 20,
                "validation": "All outputs bitwise identical (timing stripped)",
            },
            "test_dag_replay": {
                "description": "DAG [analyze_target, trace_callers, verify.architecture] × 10 runs",
                "runs": 10,
                "validation": "Combined outputs bitwise identical (timing stripped)",
            },
            "test_partitioned_replay": {
                "description": "Partition optimizer × 10 runs + partition execution × 10 runs",
                "runs": 10,
                "validation": "Partitions stable, execution outputs identical",
            },
            "test_optimizer_replay": {
                "description": "Optimizer pure function × 10 runs (dedup + folding edge cases)",
                "runs": 10,
                "validation": "OptimizationResult fully bitwise identical",
            },
            "test_cache_conscious_replay": {
                "description": "Cache population, fold detection, warm-run replay consistency",
                "runs": 10,
                "validation": "Cache populated, cache_hits > 0 on warm runs, non-folded outputs stable",
            },
            "test_parallel_vs_serial_equivalence": {
                "description": "DAG vs serial vs reverse order execution",
                "runs": 3,
                "validation": "Logical outputs identical regardless of order",
            },
            "test_cross_run_telemetry_consistency": {
                "description": "Telemetry counters × 5 runs with documentation of variation",
                "runs": 5,
                "validation": "Deterministic counters stable, estimated_speedup may vary",
            },
        },
        "non_determinism_documented": [
            "_duration_ms — wall-clock timing, varies per execution (stripped by _json_hash)",
            "trace_id / timestamp — run-level nonces (stripped by _json_hash)",
            "estimated_speedup — may vary with cache state or cost metadata",
            "Primitives with empty input_keys (verify.architecture) "
            "cannot be folded (fingerprint is empty string)",
            "When ALL primitives are folded, execution loop is empty "
            "and no cache merge occurs (known engine edge case)",
            "Primitive output keys may overlap between verify primitives "
            "(dict.update last-writer-wins)",
            "build_execution_dag is pure — same inputs always produce same stages",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[replay] Report saved to {report_path}")

    # Also handle --report flag for failure benchmarks
    if hasattr(session.config, "_recovery_score"):
        from test_failure_benchmarks import format_recovery_report
        score = session.config._recovery_score
        print("\n\n" + "=" * 72)
        print("  AIHELPER ADVERSARIAL FAILURE BENCHMARK — RECOVERY REPORT")
        print("=" * 72)
        print()
        print(format_recovery_report(score))
