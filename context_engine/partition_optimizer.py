"""
Execution Partition Optimizer — automatically SHARDS primitive execution into
isolated partitions based on the dependency graph.

Inspired by database query partitioning and compiler parallel region analysis.

Core insight: if two primitives operate on disjoint sets of symbols/files and
share no data dependencies, they can execute in completely independent partitions
— enabling parallel execution without coordination overhead.

Architecture:
  1. analyze_dependency_graph  — build A→B dependency map from input/output keys
  2. detect_isolated_regions  — find connected components (partitions)
  3. compute_parallel_groups  — determine which partitions can run in parallel
  4. _compute_critical_path   — longest chain (theoretical lower bound on time)
  5. optimize_partitions      — orchestrator returning PartitionResult
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .primitives import get_registry


# ── Result Dataclass ────────────────────────────────────────────

@dataclass
class PartitionResult:
    """Result of partition optimization analysis.

    Provides full visibility into how the primitive set was partitioned,
    which groups can execute in parallel, and the expected speedup.
    """
    partitions: List[List[str]] = field(default_factory=list)
    parallel_groups: List[List[int]] = field(default_factory=list)
    critical_path: List[str] = field(default_factory=list)
    estimated_speedup: float = 1.0
    partition_count: int = 0
    max_partition_size: int = 0

    @property
    def is_single_partition(self) -> bool:
        """True when all primitives collapsed into one partition."""
        return self.partition_count <= 1

    @property
    def is_fully_parallel(self) -> bool:
        """True when every partition can run independently."""
        total = self.partition_count
        if total <= 1:
            return False
        # Fully parallel means all partitions are in a single parallel group
        flat = set()
        for group in self.parallel_groups:
            flat.update(group)
        return len(flat) == total

    @property
    def max_parallelism(self) -> int:
        """Maximum number of partitions that can run simultaneously."""
        return max((len(g) for g in self.parallel_groups), default=1)

    def to_dict(self) -> Dict[str, Any]:
        """Serializable dict for profiling / daemon responses."""
        return {
            "partitions": self.partitions,
            "parallel_groups": self.parallel_groups,
            "critical_path": self.critical_path,
            "estimated_speedup": round(self.estimated_speedup, 2),
            "partition_count": self.partition_count,
            "max_partition_size": self.max_partition_size,
            "is_single_partition": self.is_single_partition,
            "is_fully_parallel": self.is_fully_parallel,
            "max_parallelism": self.max_parallelism,
        }


# ── Public API ──────────────────────────────────────────────────

def analyze_dependency_graph(primitives: List[str],
                             project_root: Optional[Path] = None) -> Dict[str, Set[str]]:
    """Build a dependency map between primitives based on input/output keys.

    A → B if B's input_keys contains any of A's output_keys.
    Also considers explicit `depends_on` contract declarations.

    Returns {primitive_name: {dependent_primitive_names}}.
    The graph is directed: key depends on each value in its set.
    """
    reg = get_registry()
    # Collect output_keys for each primitive
    outputs: Dict[str, Set[str]] = {}
    inputs: Dict[str, Set[str]] = {}

    for name in primitives:
        prim = reg.get(name)
        if prim is None:
            outputs[name] = set()
            inputs[name] = set()
            continue
        outputs[name] = set(prim.contract.output_keys)
        inputs[name] = set(prim.contract.input_keys)

    # Build reverse map: which primitives could satisfy each output key?
    key_to_producers: Dict[str, List[str]] = {}
    for name, out_keys in outputs.items():
        for k in out_keys:
            key_to_producers.setdefault(k, []).append(name)

    # Build dependency graph: A → B if B needs A's outputs
    dep_graph: Dict[str, Set[str]] = {name: set() for name in primitives}

    for name in primitives:
        in_keys = inputs.get(name, set())
        for k in in_keys:
            producers = key_to_producers.get(k, [])
            for producer in producers:
                if producer != name:
                    dep_graph[name].add(producer)

    # Also incorporate explicit depends_on declarations
    for name in primitives:
        prim = reg.get(name)
        if prim is None:
            continue
        for dep in prim.contract.depends_on:
            if dep in primitives:
                dep_graph[name].add(dep)

    return dep_graph


def detect_isolated_regions(dep_graph: Dict[str, Set[str]]) -> List[List[str]]:
    """Find connected components (isolated regions) in the dependency graph.

    Uses BFS on the underlying undirected graph.
    Each region is a list of primitives that share transitive dependencies.
    Regions with no cross-dependencies can execute in parallel partitions.
    """
    # Build undirected adjacency for component detection
    nodes = list(dep_graph.keys())
    adj: Dict[str, Set[str]] = {n: set(dep_graph[n]) for n in nodes}

    # Add reverse edges to make it undirected
    for name, deps in dep_graph.items():
        for dep in deps:
            if dep in adj:
                adj[dep].add(name)

    components = _find_connected_components(adj)

    # Sort each component deterministically
    result = [sorted(comp) for comp in components]
    # Sort components by size descending, then by first element name
    result.sort(key=lambda c: (-len(c), c[0] if c else ""))
    return result


def optimize_partitions(primitives: List[str],
                        context: Dict[str, Any],
                        project_root: Path) -> PartitionResult:
    """Main function: analyze → detect → optimize → return PartitionResult.

    Full pipeline:
      1. Build dependency graph from primitive contracts
      2. Detect isolated regions (connected components)
      3. Compute parallel groups (non-overlapping regions)
      4. Compute critical path (longest chain through the graph)
      5. Estimate speedup from parallel execution
    """
    if not primitives:
        return PartitionResult()

    # Step 1: Build dependency graph
    dep_graph = analyze_dependency_graph(primitives, project_root)

    # Step 2: Detect isolated regions (partitions)
    partitions = detect_isolated_regions(dep_graph)

    # Step 3: Compute which partitions can run in parallel.
    # Since regions are disconnected, ALL partitions can run in parallel
    # as long as they have no intra-partition dependencies.
    # BUT: a partition must wait for another if any primitive in it depends
    # on a primitive in the other partition.
    parallel_groups = _compute_parallel_groups(partitions, dep_graph)

    # Step 4: Compute critical path
    critical_path = _compute_critical_path(dep_graph)

    # Step 5: Estimate speedup
    estimated_speedup = _estimate_speedup(primitives, partitions, parallel_groups)

    partition_count = len(partitions)
    max_partition_size = max((len(p) for p in partitions), default=0)

    # ── Runtime event: partition created ──
    try:
        from .event_bus import get_event_bus, PARTITION_CREATED
        _pb = get_event_bus()
        _pb.emit(PARTITION_CREATED, {
            "partition_count": partition_count,
            "sizes": [len(p) for p in partitions],
            "max_partition_size": max_partition_size,
            "parallel_groups": len(parallel_groups),
            "critical_path_length": len(critical_path),
            "estimated_speedup": estimated_speedup,
            "max_parallelism": len(parallel_groups),
        })
    except Exception:
        pass

    return PartitionResult(
        partitions=partitions,
        parallel_groups=parallel_groups,
        critical_path=critical_path,
        estimated_speedup=estimated_speedup,
        partition_count=partition_count,
        max_partition_size=max_partition_size,
    )


# ── Private Helpers ─────────────────────────────────────────────

def _find_connected_components(graph: Dict[str, Set[str]]) -> List[Set[str]]:
    """Find connected components in an undirected graph using BFS.

    Args:
        graph: {node: {neighbor, ...}} — undirected adjacency.

    Returns:
        List of connected component sets.
    """
    visited: Set[str] = set()
    components: List[Set[str]] = []

    for node in graph:
        if node in visited:
            continue
        # BFS from this node
        component: Set[str] = set()
        queue: deque = deque([node])
        visited.add(node)

        while queue:
            current = queue.popleft()
            component.add(current)
            for neighbor in graph.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        components.append(component)

    return components


def _compute_parallel_groups(
    partitions: List[List[str]],
    dep_graph: Dict[str, Set[str]],
) -> List[List[int]]:
    """Determine which partition indices can execute in parallel.

    Builds a partition-level dependency graph, then groups partitions
    into parallel execution layers (like build_execution_dag but at
    partition granularity).

    Returns a list of lists of partition indices. Each inner list is
    a set of partitions that can run simultaneously.
    """
    if not partitions:
        return []

    # Build partition index lookup
    prim_to_partition: Dict[str, int] = {}
    for i, partition in enumerate(partitions):
        for prim_name in partition:
            prim_to_partition[prim_name] = i

    # Build partition-level dependency: partition P → partition Q
    # if a primitive in P depends on a primitive in Q
    partition_deps: Dict[int, Set[int]] = {i: set() for i in range(len(partitions))}

    for prim_name, deps in dep_graph.items():
        p_idx = prim_to_partition.get(prim_name)
        if p_idx is None:
            continue
        for dep in deps:
            q_idx = prim_to_partition.get(dep)
            if q_idx is not None and q_idx != p_idx:
                partition_deps[p_idx].add(q_idx)

    # Topological layering: BFS layers
    # Each layer = set of partitions whose deps are all in earlier layers
    remaining: Set[int] = set(range(len(partitions)))
    layers: List[List[int]] = []

    while remaining:
        layer: List[int] = []
        for p_idx in list(remaining):
            # Can this partition run now? All its deps must be done.
            deps = partition_deps.get(p_idx, set())
            if not (deps & remaining):  # no remaining dependencies
                layer.append(p_idx)

        if not layer:
            # Cycle or unresolvable — add all remaining
            layer = list(remaining)

        for p_idx in layer:
            remaining.remove(p_idx)
        layers.append(layer)

    return layers


def _compute_critical_path(dep_graph: Dict[str, Set[str]]) -> List[str]:
    """Compute the longest path through the dependency graph.

    Uses DP on topologically sorted DAG.
    Returns the longest chain of primitives (names in order).

    If the graph has cycles, falls back to heuristic: longest simple path
    via DFS with visited tracking.
    """
    if not dep_graph:
        return []

    # Try topological sort first (fails on cycles)
    ordered = _topological_sort(dep_graph)

    if ordered is not None:
        return _longest_path_dp(dep_graph, ordered)
    else:
        # Cycle detected — use DFS-based longest simple path heuristic
        return _longest_path_dfs(dep_graph)


def _topological_sort(graph: Dict[str, Set[str]]) -> Optional[List[str]]:
    """Kahn's algorithm for topological sort. Returns None if cycle exists."""
    in_degree: Dict[str, int] = {n: 0 for n in graph}
    for deps in graph.values():
        for dep in deps:
            if dep in in_degree:
                in_degree[dep] += 1

    queue: deque = deque([n for n, d in in_degree.items() if d == 0])
    sorted_nodes: List[str] = []

    while queue:
        node = queue.popleft()
        sorted_nodes.append(node)
        for dep in graph.get(node, set()):
            if dep in in_degree:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

    if len(sorted_nodes) != len(graph):
        return None  # cycle detected

    return sorted_nodes


def _longest_path_dp(graph: Dict[str, Set[str]],
                     topo_order: List[str]) -> List[str]:
    """DP longest path in a DAG. Returns the path (list of node names)."""
    dist: Dict[str, int] = {n: 0 for n in graph}
    predecessor: Dict[str, Optional[str]] = {n: None for n in graph}

    for node in topo_order:
        for dep in graph.get(node, set()):
            if dep in dist and dist[dep] < dist[node] + 1:
                dist[dep] = dist[node] + 1
                predecessor[dep] = node

    # Find the farthest node
    max_dist = -1
    end_node: Optional[str] = None
    for node, d in dist.items():
        if d > max_dist:
            max_dist = d
            end_node = node

    if end_node is None:
        return []

    # Reconstruct path
    path: List[str] = []
    current: Optional[str] = end_node
    while current is not None:
        path.append(current)
        current = predecessor.get(current)

    path.reverse()
    return path


def _longest_path_dfs(graph: Dict[str, Set[str]]) -> List[str]:
    """DFS-based longest simple path heuristic for cyclic graphs.

    Since longest path in a general graph is NP-hard, this returns
    a greedy longest path from each start node.
    """
    visited_global: Set[str] = set()
    best_path: List[str] = []

    def dfs(current: str, path: List[str], visited: Set[str]) -> None:
        nonlocal best_path
        if len(path) > len(best_path):
            best_path = list(path)

        for neighbor in graph.get(current, set()):
            if neighbor not in visited and neighbor in graph:
                visited.add(neighbor)
                dfs(neighbor, path + [neighbor], visited)
                visited.remove(neighbor)

    for node in graph:
        if node not in visited_global:
            visited_global.add(node)
            dfs(node, [node], {node})

    return best_path


def _estimate_speedup(primitives: List[str],
                      partitions: List[List[str]],
                      parallel_groups: List[List[int]]) -> float:
    """Estimate parallel speedup factor from partition optimization.

    Uses Amdahl's law with primitive cost estimates:
      - Sum all primitive costs (serial runtime)
      - Find the critical path cost (parallel runtime bound)
      - speedup = serial / parallel

    Falls back to partition count heuristic when costs are unavailable.
    """
    reg = get_registry()

    def _cost(name: str) -> float:
        prim = reg.get(name)
        if prim is None:
            return 1.0
        return max(prim.contract.cost_estimate_ms, 0.1)

    total_serial_cost = sum(_cost(n) for n in primitives)

    if not total_serial_cost:
        # Fallback: use partition count as heuristic
        if len(partitions) <= 1:
            return 1.0
        return min(float(len(partitions)), 8.0)  # cap at 8x for heuristic

    # Compute parallel runtime cost: sum of costs along the critical path of
    # partitions, with each partition's intra-cost spread across parallel groups.

    # Build partition-level cost map
    partition_costs: List[float] = [
        sum(_cost(n) for n in part) for part in partitions
    ]

    # In each parallel group, the slowest partition determines the group cost
    parallel_cost = 0.0
    for group in parallel_groups:
        group_cost = max((partition_costs[i] for i in group), default=0.0)
        parallel_cost += group_cost

    if parallel_cost <= 0:
        return 1.0

    speedup = total_serial_cost / parallel_cost
    return round(min(speedup, 32.0), 2)  # cap at 32x theoretical max


# ── Daemon Handlers ─────────────────────────────────────────────

def handle_partition_analyze(params: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze primitives without modifying execution.

    Returns partition analysis only — no execution performed.

    Params:
        primitives: List[str] — primitive names to analyze
        project_root: optional str — override project root

    Returns:
        Dict with partition analysis + metadata
    """
    primitives: List[str] = params.get("primitives", [])
    project_root = Path(params.get("project_root", Path.cwd()))

    if not primitives:
        return {"error": "No primitives provided", "primitives": []}

    dep_graph = analyze_dependency_graph(primitives, project_root)
    partitions = detect_isolated_regions(dep_graph)
    parallel_groups = _compute_parallel_groups(partitions, dep_graph)
    critical_path = _compute_critical_path(dep_graph)

    return {
        "primitives": primitives,
        "primitive_count": len(primitives),
        "partitions": partitions,
        "partition_count": len(partitions),
        "parallel_groups": parallel_groups,
        "critical_path": critical_path,
        "max_partition_size": max((len(p) for p in partitions), default=0),
        "dependency_graph": {k: list(v) for k, v in dep_graph.items()},
    }


def handle_partition_optimize(params: Dict[str, Any]) -> Dict[str, Any]:
    """Full optimize + partition analysis.

    Runs the complete optimize_partitions pipeline.

    Params:
        primitives: List[str] — primitive names to optimize
        context: optional Dict — execution context for cost estimation
        project_root: optional str — override project root

    Returns:
        Dict with full PartitionResult data
    """
    primitives: List[str] = params.get("primitives", [])
    context: Dict[str, Any] = params.get("context", {})
    project_root = Path(params.get("project_root", Path.cwd()))

    if not primitives:
        return {"error": "No primitives provided", "result": PartitionResult().to_dict()}

    result = optimize_partitions(primitives, context, project_root)

    return {
        "primitives": primitives,
        "primitive_count": len(primitives),
        "result": result.to_dict(),
    }
