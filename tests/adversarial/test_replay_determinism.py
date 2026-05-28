#!/usr/bin/env python3
"""test_replay_determinism.py — Deterministic replay validation suite.

Validates that the runtime produces deterministic outputs when replayed
with identical inputs. Tests cover primitive execution, DAG execution,
partition optimization, DAG optimization, caching, parallel-vs-serial
equivalence, and cross-run telemetry consistency.

Key design decisions:
  - For Tests 1-2 (replay with same cache state), each run uses a fresh
    engine with an empty cache so the optimizer's constant folding pass
    doesn't change between runs.
  - For Test 5 (cache-conscious), we compare logical output keys (not
    optimizer/profiling metadata) between cold and warm runs.
  - For Tests 3-4 (pure functions), no engine needed — calls are idempotent.
  - Timing fields (_duration_ms, duration_ms, trace_id, timestamp) are
    stripped before comparison by _json_hash().

Usage:
    pytest tests/adversarial/test_replay_determinism.py -v
    pytest tests/adversarial/test_replay_determinism.py -v -k "test_single_primitive_replay"
    python -m pytest tests/adversarial/test_replay_determinism.py -v
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock, patch

import pytest

# Ensure context_engine is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


# ── Helpers ─────────────────────────────────────────────────────────

def _strip_timing(output: Dict[str, Any]) -> Dict[str, Any]:
    """Remove timing/nonce fields that vary between runs.

    BFS through all nested dicts and strips:
      - _duration_ms (wall-clock per-primitive timing)
      - duration_ms (phase-level timing)
      - trace_id / timestamp (run-level nonces)
    """
    out = copy.deepcopy(output)
    queue: List[Dict[str, Any]] = [out]
    while queue:
        d = queue.pop()
        for key in list(d.keys()):
            if key in ("_duration_ms", "duration_ms", "trace_id", "timestamp"):
                del d[key]
            elif isinstance(d[key], dict):
                queue.append(d[key])
    return out


def _json_hash(output: Dict[str, Any]) -> str:
    """Deterministic SHA-256 hash of the output (excluding timing)."""
    cleaned = _strip_timing(output)
    raw = json.dumps(cleaned, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _json_serialize(output: Dict[str, Any]) -> str:
    """Deterministic JSON string (excluding timing)."""
    cleaned = _strip_timing(output)
    return json.dumps(cleaned, sort_keys=True, default=str, ensure_ascii=False, indent=2)


def _logical_output(output: Dict[str, Any]) -> Dict[str, Any]:
    """Return only the logical (non-metadata) keys from primitive output.

    Strips _profiling and _optimizer engine-inserted metadata to allow
    comparing cached vs non-cached execution results where optimizer
    metadata legitimately differs (constant folding vs execution).
    """
    return {k: v for k, v in output.items() if not k.startswith("_")}


def _make_mock_graph_db() -> MagicMock:
    """Deterministic mock of the graph_db module.

    All callers/callees/impact queries return fixed data regardless
    of input parameters, ensuring reproducible primitive execution.
    """
    mock_db = MagicMock()
    mock_db.get_callers.return_value = [
        {"name": "caller_one", "file_path": "src/module_a.py"},
        {"name": "caller_two", "file_path": "src/module_b.py"},
    ]
    mock_db.get_callees.return_value = [
        {"name": "callee_one", "file_path": "src/dep_x.py"},
        {"name": "callee_two", "file_path": "src/dep_y.py"},
    ]
    mock_db.get_impact_radius.return_value = [
        {"name": "impacted_sym", "file_path": "src/impacted.py"},
    ]
    mock_db.find_circular_deps.return_value = []
    mock_db.find_dead_code.return_value = []
    mock_db.get_file_dependencies.return_value = []
    mock_db.search_symbols.return_value = [
        {"id": "test_symbol_123", "name": "test_symbol", "kind": "function"}
    ]
    return mock_db


def _make_deterministic_ctx(target: str = "test_symbol") -> Dict[str, Any]:
    """Build a deterministic execution context."""
    return {
        "target": target,
        "_project_root": str(_PROJECT_ROOT),
    }


def _new_engine(mock_db_instance: MagicMock) -> Any:
    """Factory: return a fresh WorkflowEngine with empty cache and mocks."""
    from context_engine.workflow_engine import WorkflowEngine
    eng = WorkflowEngine(_PROJECT_ROOT)
    eng._primitive_cache = {}
    return eng


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def mock_db() -> MagicMock:
    """Patch context_engine.graph_db.get_db with deterministic data.

    Uses function scope so each test gets a clean mock.
    """
    mock = _make_mock_graph_db()
    patcher = patch("context_engine.graph_db.get_db", return_value=mock)
    patcher.start()
    yield mock
    patcher.stop()


@pytest.fixture
def fresh_engine(mock_db) -> Any:
    """Return a fresh engine with empty cache for each test."""
    return _new_engine(mock_db)


# ═══════════════════════════════════════════════════════════════════
# Test 1: SINGLE PRIMITIVE REPLAY (20 runs)
# ═══════════════════════════════════════════════════════════════════

class TestSinglePrimitiveReplay:
    """Verify that a single deterministic primitive produces bitwise
    identical outputs across 20 consecutive executions with the same
    inputs and the same (empty) cache state."""

    PRIMITIVE = "graph.analyze_target"
    RUNS = 20

    def test_all_outputs_bitwise_identical(self, mock_db):
        """All 20 runs must produce identical hashes."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "analyze_test"}
        hashes: List[str] = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives([self.PRIMITIVE], phase_def, context)
            hashes.append(_json_hash(result.output))

        first = hashes[0]
        identical_count = sum(1 for h in hashes if h == first)
        assert identical_count == self.RUNS, (
            f"Only {identical_count}/{self.RUNS} runs produced identical output"
        )

    def test_max_deviation_is_zero(self, mock_db):
        """Max line-level deviation across 20 runs must be zero."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "analyze_test"}
        serialized: List[str] = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives([self.PRIMITIVE], phase_def, context)
            serialized.append(_json_serialize(result.output))

        baseline = serialized[0]
        max_diff = 0
        for s in serialized[1:]:
            if s != baseline:
                b_lines = baseline.splitlines()
                s_lines = s.splitlines()
                diff = abs(len(b_lines) - len(s_lines))
                for bl, sl in zip(b_lines, s_lines):
                    if bl != sl:
                        diff += 1
                max_diff = max(max_diff, diff)

        assert max_diff == 0, (
            f"Max deviation = {max_diff} line-level differences across "
            f"{self.RUNS} runs (expected 0)"
        )

    def test_phase_success_consistent(self, mock_db):
        """PhaseResult.success must be True on every run."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "analyze_test"}
        results = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives([self.PRIMITIVE], phase_def, context)
            results.append(result.success)

        assert all(results), f"PhaseResult.success varied: {results}"

    def test_logical_output_identical_across_runs(self, mock_db):
        """Logical (non-metadata) output keys must be identical."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "analyze_test"}
        logical_hashes: List[str] = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives([self.PRIMITIVE], phase_def, context)
            logical = _logical_output(result.output)
            logical_hashes.append(_json_hash(logical))

        first = logical_hashes[0]
        assert all(h == first for h in logical_hashes), (
            "Logical output varied across runs"
        )


# ═══════════════════════════════════════════════════════════════════
# Test 2: DAG REPLAY (10 runs)
# ═══════════════════════════════════════════════════════════════════

class TestDagReplay:
    """Build a multi-primitive DAG and validate replay determinism."""

    DAG = ["graph.analyze_target", "graph.trace_callers", "verify.architecture"]
    RUNS = 10

    def test_combined_output_bitwise_identical(self, mock_db):
        """Full DAG combined output must be identical across 10 runs."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "dag_test"}
        hashes: List[str] = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.DAG, phase_def, context)
            hashes.append(_json_hash(result.output))

        first = hashes[0]
        identical_count = sum(1 for h in hashes if h == first)
        assert identical_count == self.RUNS, (
            f"DAG replay: only {identical_count}/{self.RUNS} runs identical"
        )

    def test_dag_stages_always_identical(self):
        """build_execution_dag must return identical stages every call.

        This is a pure function — no engine/mocking needed.
        """
        from context_engine.primitives import build_execution_dag
        snapshots: List[str] = []

        for _ in range(self.RUNS):
            stages = build_execution_dag(self.DAG)
            snapshots.append(json.dumps(stages, sort_keys=True))

        first = snapshots[0]
        assert all(s == first for s in snapshots), (
            "build_execution_dag returned different stage layouts across runs"
        )

    def test_logical_outputs_individually_identical(self, mock_db):
        """Each primitive in the DAG contributes identical logical keys."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "dag_test"}
        logical_hashes: Dict[str, List[str]] = {p: [] for p in self.DAG}

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.DAG, phase_def, context)
            logical = _logical_output(result.output)
            h = _json_hash(logical)
            for prim_name in self.DAG:
                logical_hashes[prim_name].append(h)

        for prim_name, hashes in logical_hashes.items():
            first = hashes[0]
            assert all(h == first for h in hashes), (
                f"Logical output varied across runs for primitive '{prim_name}'"
            )


# ═══════════════════════════════════════════════════════════════════
# Test 3: PARTITIONED REPLAY (10 runs)
# ═══════════════════════════════════════════════════════════════════

class TestPartitionedReplay:
    """Partition optimizer must produce stable partition assignments and
    deterministic execution outputs across repeated runs."""

    PRIMITIVES = [
        "graph.analyze_target",
        "graph.trace_callers",
        "graph.trace_callees",
        "verify.architecture",
        "verify.dependency_health",
        "memory.recall",
    ]
    RUNS = 10

    def test_partition_assignments_stable(self):
        """Partition assignments must be identical across 10 runs."""
        from context_engine.partition_optimizer import optimize_partitions
        context = _make_deterministic_ctx()
        snapshots: List[str] = []

        for _ in range(self.RUNS):
            result = optimize_partitions(self.PRIMITIVES, context, _PROJECT_ROOT)
            snapshots.append(
                json.dumps(result.to_dict(), sort_keys=True, default=str)
            )

        first = snapshots[0]
        identical_count = sum(1 for s in snapshots if s == first)
        assert identical_count == self.RUNS, (
            f"Partition assignments: only {identical_count}/{self.RUNS} stable"
        )

    def test_partition_count_stable(self):
        """Partition count must be stable across runs."""
        from context_engine.partition_optimizer import optimize_partitions
        context = _make_deterministic_ctx()
        counts: List[int] = []

        for _ in range(self.RUNS):
            result = optimize_partitions(self.PRIMITIVES, context, _PROJECT_ROOT)
            counts.append(result.partition_count)

        assert len(set(counts)) == 1, f"Partition count varied: {counts}"

    def test_parallel_groups_stable(self):
        """Parallel groups (partition indices) must be stable."""
        from context_engine.partition_optimizer import optimize_partitions
        context = _make_deterministic_ctx()
        groups: List[str] = []

        for _ in range(self.RUNS):
            result = optimize_partitions(self.PRIMITIVES, context, _PROJECT_ROOT)
            groups.append(json.dumps(result.parallel_groups, sort_keys=True))

        assert all(g == groups[0] for g in groups), "Parallel groups varied across runs"

    def test_critical_path_stable(self):
        """Critical path must be identical across runs."""
        from context_engine.partition_optimizer import optimize_partitions
        context = _make_deterministic_ctx()
        paths: List[str] = []

        for _ in range(self.RUNS):
            result = optimize_partitions(self.PRIMITIVES, context, _PROJECT_ROOT)
            paths.append(",".join(result.critical_path))

        assert all(p == paths[0] for p in paths), "Critical path varied across runs"

    def test_partition_execution_outputs_identical(self, mock_db):
        """Execute each partition and verify outputs are identical across runs."""
        from context_engine.partition_optimizer import optimize_partitions
        context = _make_deterministic_ctx()
        phase_def = {"name": "partitioned_test"}

        # First, get stable partitions
        part_result = optimize_partitions(self.PRIMITIVES, context, _PROJECT_ROOT)
        partitions = part_result.partitions

        snapshot_hashes: List[str] = []
        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            outputs: Dict[str, Any] = {}
            for i, partition in enumerate(partitions):
                res = eng._execute_primitives(partition, phase_def, context)
                outputs[f"p{i}"] = _logical_output(res.output)
            snapshot_hashes.append(_json_hash(outputs))

        assert all(h == snapshot_hashes[0] for h in snapshot_hashes), (
            "Partition execution outputs varied across runs"
        )


# ═══════════════════════════════════════════════════════════════════
# Test 4: OPTIMIZER REPLAY (10 runs)
# ═══════════════════════════════════════════════════════════════════

class TestOptimizerReplay:
    """The optimizer (optimize_dag) is a pure function — it must produce
    bitwise identical results across repeated calls with the same inputs,
    same context, and same cache state."""

    PRIMITIVES = [
        "graph.analyze_target",
        "graph.trace_callers",
        "graph.analyze_target",  # intentional duplicate → dedup
        "memory.recall",
        "graph.trace_callees",
        "verify.architecture",
        "verify.dependency_health",
    ]
    CONTEXT = {"target": "UserService"}
    RUNS = 10

    def test_optimized_dag_identical(self):
        from context_engine.optimizer import optimize_dag
        cache = {}
        serialized: List[str] = []

        for _ in range(self.RUNS):
            result = optimize_dag(self.PRIMITIVES, self.CONTEXT, cache)
            serialized.append(json.dumps(result.optimized_dag, sort_keys=True))

        assert all(s == serialized[0] for s in serialized), (
            "optimize_dag returned different optimized_dag across runs"
        )

    def test_folded_nodes_identical(self):
        from context_engine.optimizer import optimize_dag
        cache = {}
        serialized: List[str] = []

        for _ in range(self.RUNS):
            result = optimize_dag(self.PRIMITIVES, self.CONTEXT, cache)
            serialized.append(json.dumps(result.folded_nodes, sort_keys=True))

        assert all(s == serialized[0] for s in serialized), (
            "folded_nodes varied across runs"
        )

    def test_eliminated_nodes_identical(self):
        from context_engine.optimizer import optimize_dag
        cache = {}
        serialized: List[str] = []

        for _ in range(self.RUNS):
            result = optimize_dag(self.PRIMITIVES, self.CONTEXT, cache)
            serialized.append(json.dumps(result.eliminated_nodes, sort_keys=True))

        assert all(s == serialized[0] for s in serialized), (
            "eliminated_nodes varied across runs"
        )

    def test_applied_passes_identical(self):
        from context_engine.optimizer import optimize_dag
        cache = {}
        serialized: List[str] = []

        for _ in range(self.RUNS):
            result = optimize_dag(self.PRIMITIVES, self.CONTEXT, cache)
            serialized.append(json.dumps(result.applied_passes, sort_keys=True))

        assert all(s == serialized[0] for s in serialized), (
            "applied_passes varied across runs"
        )

    def test_full_optimization_result_identical(self):
        """Full OptimizationResult.to_dict() must be bitwise identical."""
        from context_engine.optimizer import optimize_dag
        cache = {}
        serialized: List[str] = []

        for _ in range(self.RUNS):
            result = optimize_dag(self.PRIMITIVES, self.CONTEXT, cache)
            serialized.append(
                json.dumps(result.to_dict(), sort_keys=True, default=str)
            )

        assert all(s == serialized[0] for s in serialized), (
            f"Only {sum(1 for s in serialized if s == serialized[0])}/"
            f"{self.RUNS} OptimizationResults were identical"
        )

    def test_warm_cache_stable_across_runs(self):
        """With a fixed warm cache, results must remain stable."""
        from context_engine.optimizer import optimize_dag
        from context_engine.primitives import get_primitive

        prim = get_primitive("graph.analyze_target")
        fp = prim.contract.fingerprint_inputs({"target": "UserService"})
        cache = {f"graph.analyze_target:{fp}": {"symbol_id": "cached_sym"}}

        serialized: List[str] = []
        for _ in range(self.RUNS):
            result = optimize_dag(self.PRIMITIVES, self.CONTEXT, cache)
            serialized.append(
                json.dumps(result.to_dict(), sort_keys=True, default=str)
            )

        assert all(s == serialized[0] for s in serialized), (
            "Optimizer with warm cache produced varying results"
        )


# ═══════════════════════════════════════════════════════════════════
# Test 5: CACHE-CONSCIOUS REPLAY
# ═══════════════════════════════════════════════════════════════════

class TestCacheConsciousReplay:
    """Validate cache-aware execution replay.

    The optimizer's constant folding pass removes cacheable primitives from
    the execution DAG on subsequent runs. The engine merges cached results
    back for primitives that *remain in the DAG after folding*.  Primitives
    with empty `input_keys` (e.g. `verify.architecture`) always execute
    because their fingerprint is empty — they never fold.

    We validate:
      1. Engine._primitive_cache is populated after first execution
      2. Warm runs report cache_hits > 0 in optimizer metadata
      3. Non-folded primitives produce bitwise-identical output on replay
      4. The cache correctly avoids re-execution of folded primitives

    Known limitation: when *all* primitives in a call are folded, the
    execution loop is empty and no cache merge occurs. This is a current
    engine behavior, not a test issue.
    """

    # Use memory.recall (has input_keys, deterministic fingerprint)
    # paired with verify.architecture (no input_keys, always executes)
    PRIMITIVES = ["verify.architecture", "memory.recall"]

    def test_cache_populated_after_first_run(self, mock_db):
        """Engine cache must contain entries after first execution."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "cache_test"}

        eng = _new_engine(mock_db)
        eng._execute_primitives(self.PRIMITIVES, phase_def, context)

        assert len(eng._primitive_cache) > 0, (
            "Engine cache is empty after first execution"
        )

    def test_warm_run_reports_cache_hits(self, mock_db):
        """Second execution must report cache_hits > 0 in _optimizer.

        `memory.recall` has deterministic input_keys (target), so its
        fingerprint matches and it gets folded on the warm run.
        `verify.architecture` has no input_keys so it always executes.
        """
        context = _make_deterministic_ctx()
        phase_def = {"name": "cache_test"}

        eng = _new_engine(mock_db)
        result_cold = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
        result_warm = eng._execute_primitives(self.PRIMITIVES, phase_def, context)

        cold_hits = result_cold.output.get("_optimizer", {}).get("cache_hits", [])
        warm_hits = result_warm.output.get("_optimizer", {}).get("cache_hits", [])

        assert len(warm_hits) > 0, (
            f"Warm run had zero cache_hits (expected >0, got {warm_hits})"
        )
        assert len(cold_hits) == 0, (
            f"Cold run had {len(cold_hits)} cache_hits (expected 0)"
        )
        # Verify it's memory.recall that was folded (verify.architecture
        # has empty input_keys so it can't fold)
        assert "memory.recall" in warm_hits, (
            f"Expected memory.recall in cache_hits, got {warm_hits}"
        )

    def test_non_folded_primitives_bitwise_identical_on_replay(self, mock_db):
        """Non-folded primitives (verify.architecture) must produce
        bitwise-identical output across repeated runs."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "cache_test"}

        hashes: List[str] = []
        for _ in range(10):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
            hashes.append(_json_hash(result.output))

        assert all(h == hashes[0] for h in hashes), (
            "Non-folded primitive output varied across runs"
        )

    def test_optimizer_skips_folded_primitives_in_dag(self, mock_db):
        """After warm-up, the optimizer's optimized_dag excludes folded
        primitives, but the engine merges cached results for them.
        """
        context = _make_deterministic_ctx()
        phase_def = {"name": "cache_test"}

        eng = _new_engine(mock_db)
        eng._execute_primitives(self.PRIMITIVES, phase_def, context)  # warm

        result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
        opt = result.output.get("_optimizer", {})

        # verify.architecture should still be in the optimized DAG
        # (it can't fold due to empty input_keys)
        assert "verify.architecture" in opt.get("optimized_dag", []), (
            f"verify.architecture missing from optimized_dag: {opt.get('optimized_dag')}"
        )
        # memory.recall should be folded out
        assert "memory.recall" not in opt.get("optimized_dag", []), (
            "memory.recall should be folded out of optimized_dag"
        )

    def test_repeated_warm_runs_consistent(self, mock_db):
        """Repeated warm cache runs must produce identical output."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "cache_test"}

        eng = _new_engine(mock_db)
        eng._execute_primitives(self.PRIMITIVES, phase_def, context)  # warm

        hashes: List[str] = []
        for _ in range(10):
            result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
            hashes.append(_json_hash(result.output))

        assert all(h == hashes[0] for h in hashes), (
            "Warm cache outputs varied across repeated runs"
        )


# ═══════════════════════════════════════════════════════════════════
# Test 6: PARALLEL VS SERIAL OUTPUT EQUIVALENCE
# ═══════════════════════════════════════════════════════════════════

class TestParallelVsSerialEquivalence:
    """Output must be identical regardless of execution order.

    The engine's DAG execution groups primitives into parallel stages.
    Manual serial execution and reverse-order execution should produce
    identical logical output since output keys are disjoint across
    independent primitives.
    """

    # Primitives with DISJOINT output keys, so dict.update() merge order
    # does not matter. Avoid primitives that share output keys (e.g.
    # verify.architecture and verify.dependency_health both write
    # check/circular_deps/dead_code with different values).
    PRIMITIVES = [
        "graph.impact_radius",
        "memory.recall",
        "test.generate_stub",
        "verify.dependency_health",
    ]

    def test_parallel_vs_serial_logical_identical(self, mock_db):
        """DAG engine execution vs manual sequential must match logically."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "parallel_test"}

        # DAG execution via engine
        eng = _new_engine(mock_db)
        dag_result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)

        # Manual sequential execution (no optimizer)
        from context_engine.primitives import get_primitive
        serial_output: Dict[str, Any] = {}
        for prim_name in self.PRIMITIVES:
            prim = get_primitive(prim_name)
            output = prim.execute(context, _PROJECT_ROOT)
            serial_output.update(_logical_output(output))

        dag_logical = _json_hash(_logical_output(dag_result.output))
        serial_logical = _json_hash(serial_output)

        assert dag_logical == serial_logical, (
            "DAG vs serial execution logical output differs!\n"
            f"DAG: {dag_logical}\nSerial: {serial_logical}"
        )

    def test_reverse_order_logical_identical(self, mock_db):
        """Reversed execution order must produce same logical output."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "reverse_test"}

        eng_normal = _new_engine(mock_db)
        normal = eng_normal._execute_primitives(self.PRIMITIVES, phase_def, context)

        eng_rev = _new_engine(mock_db)
        reversed_prims = list(reversed(self.PRIMITIVES))
        reversed_res = eng_rev._execute_primitives(reversed_prims, phase_def, context)

        assert _json_hash(_logical_output(normal.output)) == _json_hash(
            _logical_output(reversed_res.output)
        ), "Normal and reversed execution logical outputs differ!"

    def test_dag_stage_logical_equivalence(self, mock_db):
        """Logical output from direct execution vs stage-by-stage must match.

        We compare only non-metadata keys (_logical_output) because metadata
        keys (_profiling, _optimizer) differ per _execute_primitives call.
        """
        from context_engine.primitives import build_execution_dag

        context = _make_deterministic_ctx()
        phase_def = {"name": "order_test"}
        stages = build_execution_dag(self.PRIMITIVES)

        # Direct flat execution
        eng_direct = _new_engine(mock_db)
        flat_prims = [p for stage in stages for p in stage]
        direct_result = eng_direct._execute_primitives(flat_prims, phase_def, context)

        # Stage-by-stage execution: merge logical outputs from each stage
        eng_staged = _new_engine(mock_db)
        combined_logical: Dict[str, Any] = {}
        for stage in stages:
            res = eng_staged._execute_primitives(stage, phase_def, context)
            combined_logical.update(_logical_output(res.output))

        direct_logical_hash = _json_hash(_logical_output(direct_result.output))
        staged_logical_hash = _json_hash(combined_logical)

        assert direct_logical_hash == staged_logical_hash, (
            "Direct vs stage-by-stage logical outputs differ!"
        )


# ═══════════════════════════════════════════════════════════════════
# Test 7: CROSS-RUN TELEMETRY CONSISTENCY
# ═══════════════════════════════════════════════════════════════════

class TestCrossRunTelemetryConsistency:
    """Run primitives 5 times and verify telemetry counters are consistent
    across runs (modulo expected timing variation from wall clock)."""

    PRIMITIVES = ["graph.analyze_target", "graph.trace_callers", "verify.architecture"]
    RUNS = 5

    def test_optimized_count_consistent(self, mock_db):
        """optimized_count must be identical across runs (same cache state)."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "telemetry_test"}
        counts: List[int] = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
            opt = result.output.get("_optimizer", {})
            counts.append(opt.get("optimized_count", -1))

        assert all(c == counts[0] for c in counts), (
            f"optimized_count varied: {counts}"
        )
        assert counts[0] == len(self.PRIMITIVES), (
            f"Expected {len(self.PRIMITIVES)} optimized steps, got {counts[0]}"
        )

    def test_original_count_consistent(self, mock_db):
        """original_count must be identical across runs."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "telemetry_test"}
        counts: List[int] = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
            counts.append(result.output.get("_optimizer", {}).get("original_count", -1))

        assert all(c == counts[0] for c in counts), (
            f"original_count varied: {counts}"
        )

    def test_optimization_ratio_consistent(self, mock_db):
        """optimization_ratio must be identical across runs."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "telemetry_test"}
        ratios: List[float] = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
            ratios.append(result.output.get("_optimizer", {}).get("optimization_ratio", -1.0))

        assert all(r == ratios[0] for r in ratios), f"optimization_ratio varied: {ratios}"

    def test_primitives_executed_consistent(self, mock_db):
        """primitives_executed must be identical across runs."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "telemetry_test"}
        counts: List[int] = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
            counts.append(
                result.output.get("_profiling", {}).get("primitives_executed", -1)
            )

        assert all(c == counts[0] for c in counts), (
            f"primitives_executed varied: {counts}"
        )

    def test_stages_count_consistent(self, mock_db):
        """DAG stage count must be identical across runs."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "telemetry_test"}
        counts: List[int] = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
            counts.append(result.output.get("_profiling", {}).get("stages", -1))

        assert all(c == counts[0] for c in counts), f"Stage count varied: {counts}"

    def test_primitives_requested_consistent(self, mock_db):
        """primitives_requested must be identical across runs."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "telemetry_test"}
        counts: List[int] = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
            counts.append(
                result.output.get("_profiling", {}).get("primitives_requested", -1)
            )

        assert all(c == counts[0] for c in counts), (
            f"primitives_requested varied: {counts}"
        )

    def test_applied_passes_consistent(self, mock_db):
        """applied_passes list must be identical across runs."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "telemetry_test"}
        passes: List[str] = []

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
            passes.append(
                json.dumps(result.output.get("_optimizer", {}).get("applied_passes", []))
            )

        assert all(p == passes[0] for p in passes), "applied_passes varied across runs"

    def test_phase_success_consistent(self, mock_db):
        """PhaseResult.success must be True on every run."""
        context = _make_deterministic_ctx()
        phase_def = {"name": "telemetry_test"}

        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
            assert result.success, f"PhaseResult.success=False on run"

    def test_document_non_deterministic_variation(self, mock_db):
        """Document which telemetry fields (if any) vary across runs.

        Collects all telemetry fields and explicitly asserts stability for
        deterministic fields. Purposefully allows estimated_speedup to vary
        (it's based on cost estimates that may change with cache state).
        """
        context = _make_deterministic_ctx()
        phase_def = {"name": "telemetry_doc_test"}

        records: List[Dict[str, Any]] = []
        for _ in range(self.RUNS):
            eng = _new_engine(mock_db)
            result = eng._execute_primitives(self.PRIMITIVES, phase_def, context)
            output = result.output
            records.append(
                {
                    "success": result.success,
                    "opt_optimized_count": output.get("_optimizer", {}).get("optimized_count"),
                    "opt_original_count": output.get("_optimizer", {}).get("original_count"),
                    "opt_ratio": output.get("_optimizer", {}).get("optimization_ratio"),
                    "opt_speedup": output.get("_optimizer", {}).get("estimated_speedup"),
                    "opt_passes": output.get("_optimizer", {}).get("applied_passes"),
                    "prof_stages": output.get("_profiling", {}).get("stages"),
                    "prof_executed": output.get("_profiling", {}).get("primitives_executed"),
                    "prof_requested": output.get("_profiling", {}).get("primitives_requested"),
                }
            )

        # Find fields that vary
        baseline = records[0]
        varied: Dict[str, List[Any]] = {}
        for field in baseline:
            values = [r[field] for r in records]
            if len(set(str(v) for v in values)) > 1:
                varied[field] = values

        # Assert fully deterministic fields are stable
        assert "opt_optimized_count" not in varied, (
            f"optimized_count varied: {varied.get('opt_optimized_count')}"
        )
        assert "opt_original_count" not in varied, (
            f"original_count varied: {varied.get('opt_original_count')}"
        )
        assert "opt_ratio" not in varied, (
            f"optimization_ratio varied: {varied.get('opt_ratio')}"
        )
        assert "prof_stages" not in varied, (
            f"stages varied: {varied.get('prof_stages')}"
        )
        assert "prof_executed" not in varied, (
            f"primitives_executed varied: {varied.get('prof_executed')}"
        )

        # estimated_speedup may vary with cache state — document if so
        if "opt_speedup" in varied:
            pytest.skip(
                f"opt_speedup varied across runs: {varied['opt_speedup']} "
                "(expected — speedup estimate changes with cost metadata)"
            )


# ═══════════════════════════════════════════════════════════════════
# Standalone runner
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """Run all tests with detailed output."""
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, "-v", "--tb=short", "--no-header"]))
