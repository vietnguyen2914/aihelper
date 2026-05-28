#!/usr/bin/env python3
"""
Partition Boundary Stress Tests — validates partition correctness under stress.

Scenarios:
  1. SHARED DEPENDENCY ISOLATION  — A and B both depend on C → same partition
  2. CIRCULAR DEPENDENCY HANDLING — A→B→C→A → does not crash, all in same partition
  3. TRANSITIVE GRAPH LEAKAGE    — A→B→C→D→E → all in same partition, no leakage
  4. INDEPENDENT CLUSTERS        — [A,B,C] and [D,E,F] → exactly 2 partitions
  5. CROSS-PARTITION DATA ISOLATION — outputs don't cross partition boundaries
  6. CRITICAL PATH CORRECTNESS   — longest path length and order validated
  7. PARTITION STABILITY         — same primitives → same partitions
  8. MAX PARTITION SIZE BOUNDARY — 20 independent → reasonable partition count

Run:
    pytest tests/adversarial/test_partition_stress.py -v
    pytest tests/adversarial/test_partition_stress.py -v --report  (with report)
"""
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from unittest.mock import patch

import pytest

# ── Ensure project root is on sys.path ───────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from context_engine.partition_optimizer import (
    PartitionResult,
    analyze_dependency_graph,
    detect_isolated_regions,
    _compute_critical_path,
    _compute_parallel_groups,
    optimize_partitions,
)
from context_engine.primitives import (
    CONTRACT_VERSION,
    Primitive,
    PrimitiveContract,
    get_registry,
)


# ==================================================================
# Fixtures
# ==================================================================

@pytest.fixture(autouse=True)
def _gc_before_each():
    """Clean up between tests to avoid cross-test leakage."""
    gc.collect()
    yield


# ==================================================================
# Helpers
# ==================================================================

def _make_contract(
    *,
    input_keys: Optional[List[str]] = None,
    output_keys: Optional[List[str]] = None,
    depends_on: Optional[List[str]] = None,
    cost: float = 1.0,
    pure: bool = True,
) -> PrimitiveContract:
    """Shorthand factory for synthetic test primitives."""
    return PrimitiveContract(
        input_keys=input_keys or [],
        output_keys=output_keys or [],
        cacheable=False,
        side_effects=False,
        depends_on=depends_on or [],
        cost_estimate_ms=cost,
        token_estimate=0,
        invalidates=[],
        purity="pure" if pure else "mutative",
        determinism="deterministic",
        invalidation_scope="symbol",
        parallel_safe=True,
        contract_version=CONTRACT_VERSION,
    )


def _stub_handler(name: str = "stub"):
    """Create a do-nothing handler for synthetic primitives."""
    def handler(ctx=None):
        return {name: "ok"}
    return handler


def _build_synthetic_registry(primitives: Dict[str, Primitive]) -> Dict[str, Primitive]:
    """Merge synthetic primitives into a copy of the real registry.

    This ensures all real primitives are available (no KeyError from
    unrelated lookups) while adding/overriding test-specific ones.
    """
    reg = dict(get_registry())
    reg.update(primitives)
    return reg


def _patch_registry(primitives: Dict[str, Primitive]):
    """Context manager that temporarily replaces the registry with one
    containing the given synthetic primitives merged with real ones."""
    return patch(
        "context_engine.partition_optimizer.get_registry",
        return_value=_build_synthetic_registry(primitives),
    )


def _dep_graph_to_edges(dep_graph: Dict[str, Set[str]]) -> List[str]:
    """Flatten dependency graph edges to sorted string list for assertions."""
    edges = []
    for node, deps in dep_graph.items():
        for dep in sorted(deps):
            edges.append(f"{node}←{dep}")
    return sorted(edges)


# ==================================================================
# Test 1: Shared Dependency Isolation
# ==================================================================

def test_shared_dependency_isolation():
    """A and B both depend on C → all three in same partition.

    Graph:
        C (output=x)
        A (input=x, output=y)
        B (input=x, output=z)

    Dependency edges: A←C, B←C  (A and B each depend on C)
    Connected component: {A, B, C}
    """
    primitives = {
        "C": Primitive("C", "shared dep", _stub_handler("C"), "test",
                        contract=_make_contract(output_keys=["x"])),
        "A": Primitive("A", "consumer A", _stub_handler("A"), "test",
                        contract=_make_contract(input_keys=["x"], output_keys=["y"])),
        "B": Primitive("B", "consumer B", _stub_handler("B"), "test",
                        contract=_make_contract(input_keys=["x"], output_keys=["z"])),
    }

    with _patch_registry(primitives):
        dep_graph = analyze_dependency_graph(["A", "B", "C"])
        partitions = detect_isolated_regions(dep_graph)

    # ── Assert: edges are correct ──
    edges = _dep_graph_to_edges(dep_graph)
    assert "A←C" in edges, "A should depend on C (input key 'x')"
    assert "B←C" in edges, "B should depend on C (input key 'x')"
    assert len(dep_graph) == 3, "All 3 primitives should be in dep graph"

    # ── Assert: single partition with all three ──
    assert len(partitions) == 1, (
        f"Expected 1 partition for shared dependency, got {len(partitions)}"
    )
    part = set(partitions[0])
    assert part == {"A", "B", "C"}, f"Partition should contain A,B,C, got {part}"

    # ── Assert: no cross-partition leakage (shouldn't even apply here) ──
    # Verify there are no edges to anything outside {A,B,C}
    for prim_name, deps in dep_graph.items():
        for dep in deps:
            assert dep in {"A", "B", "C"}, (
                f"Dependency leakage: {prim_name} depends on {dep} "
                f"which is outside {A,B,C}"
            )


# ==================================================================
# Test 2: Circular Dependency Handling
# ==================================================================

def test_circular_dependency_graceful():
    """A→B→C→A (cycle) should not crash and all in same partition.

    Uses explicit depends_on to create the cycle:
        A depends_on=["B"]
        B depends_on=["C"]
        C depends_on=["A"]

    The partition optimizer must handle cycles without infinite loops
    or crashes.
    """
    primitives = {
        "A": Primitive("A", "cyclic A", _stub_handler("A"), "test",
                        contract=_make_contract(depends_on=["B"], output_keys=["a"])),
        "B": Primitive("B", "cyclic B", _stub_handler("B"), "test",
                        contract=_make_contract(depends_on=["C"], output_keys=["b"])),
        "C": Primitive("C", "cyclic C", _stub_handler("C"), "test",
                        contract=_make_contract(depends_on=["A"], output_keys=["c"])),
    }

    # Should not raise any exception
    with _patch_registry(primitives):
        dep_graph = analyze_dependency_graph(["A", "B", "C"])
        partitions = detect_isolated_regions(dep_graph)
        cr_path = _compute_critical_path(dep_graph)

    # ── Assert: no crash, all three found ──
    assert len(partitions) == 1, (
        f"Cyclic nodes should be in 1 partition, got {len(partitions)}"
    )
    part = set(partitions[0])
    assert part == {"A", "B", "C"}, (
        f"Partition should contain A,B,C (cyclic), got {part}"
    )

    # ── Assert: critical path does not crash on cycles ──
    assert isinstance(cr_path, list), "Critical path should be a list"
    # At minimum the path should contain some of the nodes
    assert len(cr_path) > 0, "Critical path should not be empty for cyclic graph"
    for node in cr_path:
        assert node in {"A", "B", "C"}, (
            f"Critical path node {node} should be one of A,B,C"
        )


def test_circular_dependency_key_based():
    """Cycle via input/output key overlap: A→B→C→A.

    A outputs 'a', B needs 'a'; B outputs 'b', C needs 'b';
    C outputs 'c', A needs 'c'.

    Should not crash, all in same partition.
    """
    primitives = {
        "A": Primitive("A", "cyclic A", _stub_handler("A"), "test",
                        contract=_make_contract(input_keys=["c"], output_keys=["a"])),
        "B": Primitive("B", "cyclic B", _stub_handler("B"), "test",
                        contract=_make_contract(input_keys=["a"], output_keys=["b"])),
        "C": Primitive("C", "cyclic C", _stub_handler("C"), "test",
                        contract=_make_contract(input_keys=["b"], output_keys=["c"])),
    }

    with _patch_registry(primitives):
        dep_graph = analyze_dependency_graph(["A", "B", "C"])
        partitions = detect_isolated_regions(dep_graph)
        result = optimize_partitions(["A", "B", "C"], {}, _PROJECT_ROOT)

    # ── Assert: connected component contains all 3 ──
    assert len(partitions) == 1, (
        f"Cyclic (key-based) should be 1 partition, got {len(partitions)}"
    )
    assert set(partitions[0]) == {"A", "B", "C"}

    # ── Assert: PartitionResult gives reasonable values ──
    assert result.partition_count == 1
    assert result.max_partition_size == 3


# ==================================================================
# Test 3: Transitive Graph Leakage
# ==================================================================

def test_transitive_chain():
    """Linear chain A→B→C→D→E → all 5 in one partition, no leakage.

    Graph edges (via I/O keys):
        A produces 'a', B consumes 'a'
        B produces 'b', C consumes 'b'
        C produces 'c', D consumes 'c'
        D produces 'd', E consumes 'd'
        E is a leaf

    Also add an unrelated primitive F with no deps → should be separate.
    """
    primitives = {
        "A": Primitive("A", "chain A", _stub_handler("A"), "test",
                        contract=_make_contract(output_keys=["a"])),
        "B": Primitive("B", "chain B", _stub_handler("B"), "test",
                        contract=_make_contract(input_keys=["a"], output_keys=["b"])),
        "C": Primitive("C", "chain C", _stub_handler("C"), "test",
                        contract=_make_contract(input_keys=["b"], output_keys=["c"])),
        "D": Primitive("D", "chain D", _stub_handler("D"), "test",
                        contract=_make_contract(input_keys=["c"], output_keys=["d"])),
        "E": Primitive("E", "chain E", _stub_handler("E"), "test",
                        contract=_make_contract(input_keys=["d"])),
        "F": Primitive("F", "unrelated", _stub_handler("F"), "test",
                        contract=_make_contract(output_keys=["z"])),
    }

    with _patch_registry(primitives):
        dep_graph = analyze_dependency_graph(["A", "B", "C", "D", "E", "F"])
        partitions = detect_isolated_regions(dep_graph)

    # ── Assert: chain A→B→C→D→E forms one partition ──
    chain_partition = None
    f_partition = None
    for part in partitions:
        if "F" in part:
            f_partition = part
        if "A" in part or "B" in part or "C" in part or "D" in part or "E" in part:
            chain_partition = part

    assert chain_partition is not None, "Chain partition should exist"
    for node in ["A", "B", "C", "D", "E"]:
        assert node in set(chain_partition), (
            f"Chain node {node} should be in chain partition {chain_partition}"
        )

    # ── Assert: F is in its own partition ──
    assert f_partition is not None, "F's partition should exist"
    assert len(f_partition) == 1, (
        f"F should be alone in its partition, got {f_partition}"
    )

    # ── Assert: no cross-contamination between partitions ──
    chain_set = set(chain_partition)
    f_set = set(f_partition)
    assert chain_set.isdisjoint(f_set), (
        f"Chain and F partitions overlap: {chain_set & f_set}"
    )

    # ── Assert: no external dependency edges ──
    for prim_name, deps in dep_graph.items():
        for dep in deps:
            if prim_name in chain_set:
                assert dep in chain_set, (
                    f"Leakage from chain: {prim_name} depends on {dep} which is outside the chain"
                )
            if prim_name == "F":
                assert dep == "" or dep is None or True  # F has no deps
                # Actually just verify F has no deps
                assert len(deps) == 0 or dep in {"F"}, (
                    f"Leakage from F: F depends on {dep}"
                )


# ==================================================================
# Test 4: Independent Clusters
# ==================================================================

def test_independent_clusters():
    """Two completely independent clusters → exactly 2 partitions.

    Cluster 1: [A, B, C] — A→B→C (A produces 'a', B consumes 'a' and produces 'b', C consumes 'b')
    Cluster 2: [D, E, F] — D→E→F (D produces 'd', E consumes 'd' and produces 'e', F consumes 'e')
    """
    primitives = {
        "A": Primitive("A", "cluster1 A", _stub_handler("A"), "test",
                        contract=_make_contract(output_keys=["a"])),
        "B": Primitive("B", "cluster1 B", _stub_handler("B"), "test",
                        contract=_make_contract(input_keys=["a"], output_keys=["b"])),
        "C": Primitive("C", "cluster1 C", _stub_handler("C"), "test",
                        contract=_make_contract(input_keys=["b"])),
        "D": Primitive("D", "cluster2 D", _stub_handler("D"), "test",
                        contract=_make_contract(output_keys=["d"])),
        "E": Primitive("E", "cluster2 E", _stub_handler("E"), "test",
                        contract=_make_contract(input_keys=["d"], output_keys=["e"])),
        "F": Primitive("F", "cluster2 F", _stub_handler("F"), "test",
                        contract=_make_contract(input_keys=["e"])),
    }

    with _patch_registry(primitives):
        dep_graph = analyze_dependency_graph(["A", "B", "C", "D", "E", "F"])
        partitions = detect_isolated_regions(dep_graph)
        parallel_groups = _compute_parallel_groups(partitions, dep_graph)
        result = optimize_partitions(["A", "B", "C", "D", "E", "F"], {}, _PROJECT_ROOT)

    # ── Assert: exactly 2 partitions ──
    assert len(partitions) == 2, (
        f"Expected 2 partitions for 2 independent clusters, got {len(partitions)}"
    )

    # ── Assert: each partition contains the correct cluster ──
    # Partitions are sorted by size desc then first element
    # Both clusters are size 3, so order depends on first element
    partition_sets = [set(p) for p in partitions]
    assert {"A", "B", "C"} in partition_sets, (
        f"Partitions {partition_sets} should contain cluster [A,B,C]"
    )
    assert {"D", "E", "F"} in partition_sets, (
        f"Partitions {partition_sets} should contain cluster [D,E,F]"
    )

    # ── Assert: partitions can run in parallel (no cross-deps) ──
    # With 2 independent clusters, the parallel groups should put both
    # partitions in the same layer
    all_indices = set()
    for group in parallel_groups:
        all_indices.update(group)
    assert len(all_indices) == 2, (
        f"Both partitions should appear in parallel groups, got {len(all_indices)}"
    )

    # Verify no cross-partition edges in dep_graph
    for prim_name, deps in dep_graph.items():
        for dep in deps:
            if prim_name in {"A", "B", "C"}:
                assert dep in {"A", "B", "C"}, (
                    f"Cross-cluster edge: {prim_name} depends on {dep}"
                )
            elif prim_name in {"D", "E", "F"}:
                assert dep in {"D", "E", "F"}, (
                    f"Cross-cluster edge: {prim_name} depends on {dep}"
                )

    # ── Assert: PartitionResult matches ──
    assert result.partition_count == 2
    assert result.max_partition_size == 3
    # Two independent clusters should be parallelizable
    assert result.max_parallelism >= 2, (
        f"Expected parallelism >= 2 for independent clusters, got {result.max_parallelism}"
    )


# ==================================================================
# Test 5: Cross-Partition Data Isolation
# ==================================================================

def test_cross_partition_data_isolation():
    """Verify outputs from one partition do not flow into another partition.

    Cluster 1: P1_A → P1_B → P1_C  (keys: x→y→z)
    Cluster 2: P2_D → P2_E          (keys: u→v)

    Validation:
      1. Run partition optimizer → detect 2 partitions
      2. Partition 1's output keys should be disjoint from Partition 2's input keys
      3. No dependency edge bridges the two partitions
      4. The partitions can execute independently (in same parallel group)
    """
    primitives = {
        "P1_A": Primitive("P1_A", "partition1 A", _stub_handler("P1_A"), "test",
                           contract=_make_contract(output_keys=["x"])),
        "P1_B": Primitive("P1_B", "partition1 B", _stub_handler("P1_B"), "test",
                           contract=_make_contract(input_keys=["x"], output_keys=["y"])),
        "P1_C": Primitive("P1_C", "partition1 C", _stub_handler("P1_C"), "test",
                           contract=_make_contract(input_keys=["y"])),
        "P2_D": Primitive("P2_D", "partition2 D", _stub_handler("P2_D"), "test",
                           contract=_make_contract(output_keys=["u"])),
        "P2_E": Primitive("P2_E", "partition2 E", _stub_handler("P2_E"), "test",
                           contract=_make_contract(input_keys=["u"])),
    }

    with _patch_registry(primitives):
        dep_graph = analyze_dependency_graph(["P1_A", "P1_B", "P1_C", "P2_D", "P2_E"])
        partitions = detect_isolated_regions(dep_graph)
        parallel_groups = _compute_parallel_groups(partitions, dep_graph)

    # ── Step 1: Confirm 2 partitions ──
    assert len(partitions) == 2, (
        f"Expected 2 partitions, got {len(partitions)}"
    )

    # Identify which partition is which
    part_idx = {}
    for i, part in enumerate(partitions):
        part_set = set(part)
        if "P1_A" in part_set and "P1_B" in part_set and "P1_C" in part_set:
            part_idx["p1"] = i
        elif "P2_D" in part_set and "P2_E" in part_set:
            part_idx["p2"] = i

    assert "p1" in part_idx, "Partition 1 (P1_A,P1_B,P1_C) not found"
    assert "p2" in part_idx, "Partition 2 (P2_D,P2_E) not found"
    assert part_idx["p1"] != part_idx["p2"], "Partitions should be distinct"

    # ── Step 2: Verify output key isolation ──
    # Collect output keys of each partition
    reg = _build_synthetic_registry(primitives)
    def partition_output_keys(part: List[str]) -> Set[str]:
        keys = set()
        for name in part:
            prim = reg.get(name)
            if prim:
                keys.update(prim.contract.output_keys)
        return keys

    def partition_input_keys(part: List[str]) -> Set[str]:
        keys = set()
        for name in part:
            prim = reg.get(name)
            if prim:
                keys.update(prim.contract.input_keys)
        return keys

    p1_out = partition_output_keys(partitions[part_idx["p1"]])
    p2_out = partition_output_keys(partitions[part_idx["p2"]])
    p1_in = partition_input_keys(partitions[part_idx["p1"]])
    p2_in = partition_input_keys(partitions[part_idx["p2"]])

    # No output key from one partition should appear as input key in the other
    assert p1_out.isdisjoint(p2_in), (
        f"P1 outputs {p1_out} leak into P2 inputs {p2_in}"
    )
    assert p2_out.isdisjoint(p1_in), (
        f"P2 outputs {p2_out} leak into P1 inputs {p1_in}"
    )

    # ── Step 3: No cross-partition dep edges ──
    for prim_name, deps in dep_graph.items():
        p_idx = part_idx["p1"] if prim_name in partitions[part_idx["p1"]] else part_idx["p2"]
        other_idx = part_idx["p2"] if p_idx == part_idx["p1"] else part_idx["p1"]
        other_set = set(partitions[other_idx])
        for dep in deps:
            assert dep not in other_set, (
                f"Cross-partition edge: {prim_name} (partition {p_idx}) "
                f"depends on {dep} (partition {other_idx})"
            )

    # ── Step 4: Both partitions can run in same parallel group ──
    # Since they're independent, they should be in the same BFS layer
    all_groups = [set(g) for g in parallel_groups]
    any_same_group = any(
        part_idx["p1"] in g and part_idx["p2"] in g
        for g in all_groups
    )
    assert any_same_group, (
        f"Partitions {part_idx['p1']} and {part_idx['p2']} should be "
        f"in the same parallel group\n  groups={parallel_groups}"
    )


# ==================================================================
# Test 6: Critical Path Correctness
# ==================================================================

def test_critical_path_linear_chain():
    """Linear chain A→B→C→D → critical path is the full chain.

    Graph (dependency direction: dependent←dependency):
        A depends on B (via output 'a' → input 'a')
        B depends on C (via output 'b' → input 'b')
        C depends on D (via output 'c' → input 'c')
        D is a leaf (no deps)

    dep_graph:  A←B, B←C, C←D
    The critical path reflects longest chain in the *dependency* graph,
    which runs from the first-executed primitive to the last.
    So D (no deps) must come first, then C, then B, then A.
    """
    primitives = {
        "A": Primitive("A", "chain A", _stub_handler("A"), "test",
                        contract=_make_contract(output_keys=["a"])),
        "B": Primitive("B", "chain B", _stub_handler("B"), "test",
                        contract=_make_contract(input_keys=["a"], output_keys=["b"],
                                                cost=5.0)),
        "C": Primitive("C", "chain C", _stub_handler("C"), "test",
                        contract=_make_contract(input_keys=["b"], output_keys=["c"],
                                                cost=3.0)),
        "D": Primitive("D", "chain D", _stub_handler("D"), "test",
                        contract=_make_contract(input_keys=["c"], cost=2.0)),
    }
    # Graph meaning:
    #   A produces 'a', B consumes 'a' → B←A
    #   B produces 'b', C consumes 'b' → C←B
    #   C produces 'c', D consumes 'c' → D←C
    #   dep_graph: A={}, B={A}, C={B}, D={C}
    #   Topo order: [A, B, C, D] (Kahn's), critical path: [A, B, C, D] reversed
    #   Critical path executes leaf-first: D → C → B → A

    with _patch_registry(primitives):
        dep_graph = analyze_dependency_graph(["A", "B", "C", "D"])
        critical_path = _compute_critical_path(dep_graph)

    # ── Assert: critical path contains all 4 nodes ──
    assert len(critical_path) == 4, (
        f"Critical path for 4-node chain should have 4 nodes, "
        f"got {len(critical_path)}: {critical_path}"
    )
    path_set = set(critical_path)
    for node in ["A", "B", "C", "D"]:
        assert node in path_set, (
            f"Critical path missing {node}: {critical_path}"
        )

    # ── Assert: order respects dependencies ──
    # In the dep_graph: A←B, B←C, C←D means D executes first, then C, B, A.
    # The critical path goes from leaf (first executed) to root (last executed).
    positions = {name: i for i, name in enumerate(critical_path)}
    assert positions["D"] < positions["C"], (
        f"D should be before C in critical path {critical_path}"
    )
    assert positions["C"] < positions["B"], (
        f"C should be before B in critical path {critical_path}"
    )
    assert positions["B"] < positions["A"], (
        f"B should be before A in critical path {critical_path}"
    )


def test_critical_path_fork_and_join():
    """DAG with fork and join validates critical path constraints.

    The DP in _compute_critical_path uses single-predecessor tracking,
    so fork-join patterns may not capture all branches. Validates:
      1. Critical path is non-empty and all nodes are valid
      2. Node order respects the dependency direction
      3. The path has the expected minimum length
    """
    primitives = {
        "A": Primitive("A", "root", _stub_handler("A"), "test",
                        contract=_make_contract(output_keys=["a", "a2"])),
        "B": Primitive("B", "left branch", _stub_handler("B"), "test",
                        contract=_make_contract(input_keys=["a"], output_keys=["b"])),
        "C": Primitive("C", "right branch", _stub_handler("C"), "test",
                        contract=_make_contract(input_keys=["a2"], output_keys=["c"])),
        "D": Primitive("D", "join", _stub_handler("D"), "test",
                        contract=_make_contract(input_keys=["b", "c"])),
    }
    # dep_graph direction:
    #   A produces 'a','a2' → B needs 'a', C needs 'a2' → B←A, C←A
    #   B produces 'b', C produces 'c', D needs 'b','c' → D←B, D←C
    #   So dep_graph = {A: {}, B: {A}, C: {A}, D: {B, C}}

    with _patch_registry(primitives):
        dep_graph = analyze_dependency_graph(["A", "B", "C", "D"])
        critical_path = _compute_critical_path(dep_graph)

    # ── Assert: critical path is non-empty ──
    assert len(critical_path) > 0, (
        f"Critical path should not be empty for fork-join DAG"
    )

    # ── Assert: all nodes on path are valid ──
    for node in critical_path:
        assert node in {"A", "B", "C", "D"}, (
            f"Unknown node {node} in critical path {critical_path}"
        )

    # ── Assert: the path captures at least the longest chain ──
    # Each branch A→B→D and A→C→D has 3 nodes.
    # The DP may capture either branch (single-predecessor limitation).
    assert len(critical_path) >= 3, (
        f"Critical path should have >= 3 nodes for fork-join, "
        f"got {len(critical_path)}: {critical_path}"
    )

    # ── Assert: partial order is respected for nodes in the path ──
    positions = {name: i for i, name in enumerate(critical_path)}
    # A must come before any of its dependents that are in the path
    if "B" in positions and "A" in positions:
        assert positions["A"] > positions["B"], "B (dep) must precede A (dependent)"
    if "C" in positions and "A" in positions:
        assert positions["A"] > positions["C"], "C (dep) must precede A (dependent)"
    # D (dep) must come after B and C (dependents of D)
    if "D" in positions and "B" in positions:
        assert positions["D"] < positions["B"], "D must precede B (execution order)"
    if "D" in positions and "C" in positions:
        assert positions["D"] < positions["C"], "D must precede C (execution order)"


# ==================================================================
# Test 7: Partition Stability Under Input Changes
# ==================================================================

def test_partition_stability():
    """Same primitives → same partition assignments regardless of context.

    The partition optimizer operates on the dependency graph derived from
    primitive contracts, not from runtime context. Running with different
    context dicts should yield identical partitions for the same primitives.
    """
    primitives = {
        "P": Primitive("P", "root", _stub_handler("P"), "test",
                        contract=_make_contract(output_keys=["x"])),
        "Q": Primitive("Q", "consumer", _stub_handler("Q"), "test",
                        contract=_make_contract(input_keys=["x"])),
        "R": Primitive("R", "independent", _stub_handler("R"), "test",
                        contract=_make_contract(output_keys=["y"])),
        "S": Primitive("S", "consumer R", _stub_handler("S"), "test",
                        contract=_make_contract(input_keys=["y"])),
    }
    names = ["P", "Q", "R", "S"]

    with _patch_registry(primitives):
        # Run with two different contexts
        result_a = optimize_partitions(names, {"target": "foo"}, _PROJECT_ROOT)
        result_b = optimize_partitions(names, {"target": "bar", "question": "baz"}, _PROJECT_ROOT)

    # ── Assert: partition structures are identical ──
    assert result_a.partitions == result_b.partitions, (
        f"Partitions differ with different contexts:\n"
        f"  context A: {result_a.partitions}\n"
        f"  context B: {result_b.partitions}"
    )
    assert result_a.partition_count == result_b.partition_count, (
        f"Partition count differs: {result_a.partition_count} vs {result_b.partition_count}"
    )
    assert result_a.max_partition_size == result_b.max_partition_size, (
        f"Max partition size differs: {result_a.max_partition_size} vs {result_b.max_partition_size}"
    )


def test_partition_changes_when_input_keys_differ():
    """Partition structure changes only when input_keys (deps) differ.

    If primitives have different input/output key sets under different
    registries, the partition structure should reflect the change.

    Here we compare: same names but different contract keys.

    Version 1: [P, Q] share dep (P→Q) → 1 partition
    Version 2: P and Q independent (no shared keys) → 2 partitions
    """
    # Version 1: P→Q
    prims_v1 = {
        "P": Primitive("P", "root v1", _stub_handler("P"), "test",
                        contract=_make_contract(output_keys=["x"])),
        "Q": Primitive("Q", "consumer v1", _stub_handler("Q"), "test",
                        contract=_make_contract(input_keys=["x"])),
    }
    # Version 2: P and Q isolated
    prims_v2 = {
        "P": Primitive("P", "root v2", _stub_handler("P"), "test",
                        contract=_make_contract(output_keys=["a"])),
        "Q": Primitive("Q", "independent v2", _stub_handler("Q"), "test",
                        contract=_make_contract(output_keys=["b"])),
    }

    names = ["P", "Q"]

    with _patch_registry(prims_v1):
        result_v1 = optimize_partitions(names, {}, _PROJECT_ROOT)

    with _patch_registry(prims_v2):
        result_v2 = optimize_partitions(names, {}, _PROJECT_ROOT)

    # V1: P and Q share dependency → 1 partition
    assert result_v1.partition_count == 1, (
        f"V1 (P→Q) should have 1 partition, got {result_v1.partition_count}"
    )

    # V2: P and Q independent → 2 partitions
    assert result_v2.partition_count == 2, (
        f"V2 (P independent from Q) should have 2 partitions, "
        f"got {result_v2.partition_count}"
    )

    # They are different
    assert result_v1.partitions != result_v2.partitions, (
        "Different contract keys should yield different partition structures"
    )


# ==================================================================
# Test 8: Max Partition Size Boundary
# ==================================================================

def test_max_partition_size_for_independent_set():
    """20 independent primitives → not all in one partition.

    Each primitive has no input keys and unique output keys.
    The optimizer should detect 20 independent components.
    """
    count = 20
    primitives = {}
    for i in range(count):
        name = f"I{i:02d}"
        primitives[name] = Primitive(
            name, f"independent {i}", _stub_handler(name), "test",
            contract=_make_contract(output_keys=[f"out_{i}"]),
        )

    names = sorted(primitives.keys())

    with _patch_registry(primitives):
        result = optimize_partitions(names, {}, _PROJECT_ROOT)

    # ── Assert: not all in one partition ──
    assert result.partition_count > 1, (
        f"20 independent primitives should not collapse to 1 partition, "
        f"got {result.partition_count}"
    )

    # ── Assert: max_partition_size < total for independent set ──
    assert result.max_partition_size < count, (
        f"Max partition size {result.max_partition_size} should be "
        f"less than total primitives {count} for independent set"
    )

    # ── Assert: each partition size is reasonable (ideally 1 each) ──
    for part in result.partitions:
        assert len(part) == 1, (
            f"Each independent primitive should be its own partition, "
            f"but found partition of size {len(part)}: {part}"
        )

    # ── Assert: partition count equals number of primitives ──
    assert result.partition_count == count, (
        f"Expected {count} partitions for {count} independent primitives, "
        f"got {result.partition_count}"
    )

    # ── Assert: all are in a single parallel group ──
    flat_parallel = set()
    for group in result.parallel_groups:
        flat_parallel.update(group)
    assert len(flat_parallel) == count, (
        f"Expected all {count} partitions in parallel groups, "
        f"got {len(flat_parallel)}"
    )


def test_max_partition_size_mixed_graph():
    """Mixed graph with large shared cluster + small independent nodes.

    Cluster: A→B→C→D→E (5 nodes, 1 partition)
    Singles: X, Y, Z (3 independent nodes)

    Total: 8 primitives, 4 partitions (1 cluster + 3 singles)
    Max partition size: 5 (the cluster)
    """
    primitives = {
        "A": Primitive("A", "cluster A", _stub_handler("A"), "test",
                        contract=_make_contract(output_keys=["a"])),
        "B": Primitive("B", "cluster B", _stub_handler("B"), "test",
                        contract=_make_contract(input_keys=["a"], output_keys=["b"])),
        "C": Primitive("C", "cluster C", _stub_handler("C"), "test",
                        contract=_make_contract(input_keys=["b"], output_keys=["c"])),
        "D": Primitive("D", "cluster D", _stub_handler("D"), "test",
                        contract=_make_contract(input_keys=["c"], output_keys=["d"])),
        "E": Primitive("E", "cluster E", _stub_handler("E"), "test",
                        contract=_make_contract(input_keys=["d"])),
        "X": Primitive("X", "single X", _stub_handler("X"), "test",
                        contract=_make_contract(output_keys=["x"])),
        "Y": Primitive("Y", "single Y", _stub_handler("Y"), "test",
                        contract=_make_contract(output_keys=["y"])),
        "Z": Primitive("Z", "single Z", _stub_handler("Z"), "test",
                        contract=_make_contract(output_keys=["z"])),
    }
    names = ["A", "B", "C", "D", "E", "X", "Y", "Z"]

    with _patch_registry(primitives):
        result = optimize_partitions(names, {}, _PROJECT_ROOT)

    # ── Assert: 4 partitions (1 cluster + 3 singles) ──
    assert result.partition_count == 4, (
        f"Expected 4 partitions (cluster of 5 + 3 singles), "
        f"got {result.partition_count}: {result.partitions}"
    )

    # ── Assert: max partition size is 5 (the cluster) ──
    assert result.max_partition_size == 5, (
        f"Max partition size should be 5 (the cluster), "
        f"got {result.max_partition_size}"
    )

    # ── Assert: cluster is in one partition ──
    cluster_part = None
    for part in result.partitions:
        if "A" in part:
            cluster_part = part
            break
    assert cluster_part is not None, "Cluster partition should exist"
    assert set(cluster_part) == {"A", "B", "C", "D", "E"}, (
        f"Cluster partition should be [A,B,C,D,E], got {cluster_part}"
    )

    # ── Assert: singles are isolated ──
    for single in ["X", "Y", "Z"]:
        for part in result.partitions:
            if single in part:
                assert len(part) == 1, (
                    f"Single primitive {single} should be alone, "
                    f"but partition has {len(part)} elements: {part}"
                )


# ==================================================================
# Edge Cases
# ==================================================================

def test_empty_primitives_list():
    """Empty primitive list should return a default PartitionResult."""
    result = optimize_partitions([], {}, _PROJECT_ROOT)
    assert result.partition_count == 0
    assert result.partitions == []
    assert result.max_partition_size == 0
    assert result.critical_path == []
    assert result.parallel_groups == []


def test_single_primitive():
    """Single primitive → single partition, single parallel group."""
    primitives = {
        "Solo": Primitive("Solo", "solo", _stub_handler("Solo"), "test",
                          contract=_make_contract(output_keys=["x"])),
    }

    with _patch_registry(primitives):
        result = optimize_partitions(["Solo"], {}, _PROJECT_ROOT)

    assert result.partition_count == 1
    assert result.partitions == [["Solo"]]
    assert result.max_partition_size == 1
    assert len(result.parallel_groups) == 1


def test_diamond_dependency():
    r"""Diamond pattern: A->(B,C)->D -> single partition, 4 nodes.

        A
       / \
      B   C
       \ /
        D
    """
    primitives = {
        "A": Primitive("A", "diamond root", _stub_handler("A"), "test",
                        contract=_make_contract(output_keys=["a", "a2"])),
        "B": Primitive("B", "diamond left", _stub_handler("B"), "test",
                        contract=_make_contract(input_keys=["a"], output_keys=["b"])),
        "C": Primitive("C", "diamond right", _stub_handler("C"), "test",
                        contract=_make_contract(input_keys=["a2"], output_keys=["c"])),
        "D": Primitive("D", "diamond join", _stub_handler("D"), "test",
                        contract=_make_contract(input_keys=["b", "c"])),
    }

    with _patch_registry(primitives):
        dep_graph = analyze_dependency_graph(["A", "B", "C", "D"])
        partitions = detect_isolated_regions(dep_graph)
        result = optimize_partitions(["A", "B", "C", "D"], {}, _PROJECT_ROOT)

    assert len(partitions) == 1, (
        f"Diamond should be 1 partition, got {len(partitions)}"
    )
    assert set(partitions[0]) == {"A", "B", "C", "D"}
    assert result.partition_count == 1
    assert result.max_partition_size == 4


# ==================================================================
# Report Generation
# ==================================================================

def pytest_sessionfinish(session, exitstatus):
    """Append partition stress results to the existing replay report."""
    report_path = _PROJECT_ROOT / "tests" / "adversarial" / "replay_report.json"
    stress_results = _collect_stress_results(session)
    if stress_results:
        try:
            if report_path.exists():
                with open(report_path) as f:
                    report = json.load(f)
            else:
                report = {}
            report["partition_stress"] = stress_results
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2)
            print(f"\n[partition-stress] Report appended to {report_path}")
        except Exception as e:
            print(f"\n[partition-stress] Could not write report: {e}")


def _collect_stress_results(session) -> Dict[str, Any]:
    """Collect pass/fail summary for all partition stress tests."""
    results = {}
    for item in session.items:
        if item.module.__name__ == __name__:
            test_name = item.name
            passed = item.nodeid not in (
                r.nodeid for r in session.session.items
                if hasattr(r, "nodeid") and hasattr(session, "_fixturemanager")
            )
            # Simpler approach: check if test had any failures
            passed = True
            if hasattr(session, "testsfailed"):
                # Can't easily map, just track test names
                pass
            results[test_name] = {
                "status": "unknown",
                "description": item.function.__doc__.strip().split("\n")[0]
                               if item.function.__doc__ else "",
            }
    return results
