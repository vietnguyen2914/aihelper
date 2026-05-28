"""
Tier Enforcement / Convergence Benchmark

Proves that the tier router prevents frontier (cloud) model leakage
across 7 independent scenarios.

Each test resets tier stats and event bus state to ensure isolation.
Output: tier_convergence_report at module teardown.
"""
from __future__ import annotations

import os
import sys
import time
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ==================================================================
# Test data: task batteries
# ==================================================================

# 20 tasks matching TIER_POLICY["force_local_for"] patterns
FORCE_LOCAL_TASKS: List[str] = [
    # dto (3)
    "create DTO for User entity",
    "generate request/response DTO for Order",
    "map DTO to domain model for Product",
    # repository (3)
    "copy repository interface from template",
    "implement repository pattern for Customer",
    "extract repository base class",
    # enum (2)
    "generate enum values for OrderStatus",
    "extract enum for PaymentMethod",
    # boilerplate (3)
    "boilerplate for REST endpoint handler",
    "generate boilerplate for service layer",
    "scaffold boilerplate for middleware",
    # crud (3)
    "crud endpoint scaffold for ProductController",
    "crud operations for User management",
    "crud service generation for Invoice",
    # route (2)
    "add route for health check endpoint",
    "route registration for API v2",
    # tab_component (2)
    "extract tab component from settings page",
    "simple tab component for dashboard",
    # simple_component (2)
    "simple component for user profile card",
    "create simple component for notification badge",
]

# 10 tasks matching TIER_POLICY["frontier_only_for"] patterns (high confidence)
# NOTE: must use EXACT substring matching — the router does literal keyword checks,
# not fuzzy/regex. e.g. "cross_cutting" not "cross-cutting", "complex_logic" not "complex logic".
FRONTIER_ONLY_TASKS_HIGH_CONF: List[Tuple[str, float]] = [
    ("refactor authentication middleware to use JWT", 0.92),
    ("architecture redesign proposal for payment module", 0.95),
    ("security audit implementation for OAuth flow", 0.91),
    ("complex_logic integration for event-driven pipeline", 0.88),
    ("cross_cutting concern migration for logging framework", 0.90),
    ("impact_analysis of schema migration on reporting", 0.93),
    ("refactor legacy monolith into microservices", 0.96),
    ("security audit of data encryption at rest", 0.89),
    ("integration of third-party auth provider", 0.87),
    ("architecture review of caching strategy", 0.94),
]

# 5 tasks matching frontier_only_for with LOW confidence
# Must use exact pattern substrings (underscores, not hyphens/spaces)
FRONTIER_ONLY_TASKS_LOW_CONF: List[Tuple[str, float]] = [
    ("refactor small utility function to use arrow syntax", 0.40),
    ("impact_analysis of renaming a single variable", 0.35),
    ("security update for dependency minor version bump", 0.42),
    ("integration of simple config file change", 0.38),
    ("architecture diagram for existing single-file module", 0.45),
]

# Unknown/catch-all tasks with varying confidence
UNKNOWN_TASKS: List[Tuple[str, float, str]] = [
    ("optimize query for user dashboard", 0.75, "frontier"),
    ("fix typo in documentation", 0.10, "deterministic"),
    ("add comment to clarify logic", 0.20, "local_model"),
    ("sort imports alphabetically", 0.05, "deterministic"),
    ("update README with examples", 0.30, "local_model"),
    ("bump version in package.json", 0.10, "deterministic"),
    ("tag release candidate", 0.15, "local_model"),
    ("run garbage collection on cache", 0.05, "deterministic"),
    ("export report as CSV", 0.15, "local_model"),
    ("ping health endpoint", 0.05, "deterministic"),
]


# ==================================================================
# Helpers
# ==================================================================

def _reset_tier_stats() -> None:
    """Reset the tier_router escalation stats."""
    from context_engine import tier_router
    tier_router._escalation_stats = {
        "total_tasks": 0,
        "frontier_escalations": 0,
        "local_model_tasks": 0,
        "deterministic_tasks": 0,
        "forced_local_count": 0,
        "enforcement_failure_count": 0,
    }


def _reset_event_bus() -> None:
    """Reset the global event bus singleton (clears all events)."""
    from context_engine.event_bus import reset_event_bus
    reset_event_bus()


# ==================================================================
# Scalar result collector
# ==================================================================

@dataclass
class ConvergenceMetric:
    """Single convergence measurement."""
    name: str
    passed: bool
    actual: Any = None
    expected: Any = None
    detail: str = ""


_convergence_metrics: List[ConvergenceMetric] = []


def _record(name: str, passed: bool, *, actual: Any = None,
            expected: Any = None, detail: str = "") -> None:
    _convergence_metrics.append(ConvergenceMetric(
        name=name, passed=passed,
        actual=actual, expected=expected,
        detail=detail,
    ))


@pytest.fixture(autouse=True)
def _isolate_tests():
    """Reset tier stats and event bus before every test."""
    _reset_tier_stats()
    _reset_event_bus()
    yield


# ==================================================================
# Test 1: FORCE-LOCAL PATTERNS — 0 FRONTIER LEAKAGE
# ==================================================================

def test_1_force_local_zero_leakage():
    """
    Every force-local pattern task MUST be blocked from frontier,
    even when explicitly asked to escalate with high confidence.
    """
    from context_engine.tier_router import enforce_tier, get_escalation_stats

    blocked = 0
    frontier_leakage = 0

    for task in FORCE_LOCAL_TASKS:
        enforced_tier, reason = enforce_tier(task, "frontier", confidence=0.9)
        if enforced_tier == "local_model":
            blocked += 1
        elif enforced_tier == "frontier":
            frontier_leakage += 1

    stats = get_escalation_stats()
    enforcement_failures = stats.get("enforcement_failure_count", 0)

    assert frontier_leakage == 0, (
        f"Frontier leakage detected: {frontier_leakage}/{len(FORCE_LOCAL_TASKS)} "
        f"force-local tasks leaked to frontier"
    )
    assert blocked == 20, (
        f"Expected 20 blocked tasks, got {blocked}"
    )
    assert enforcement_failures == 20, (
        f"enforcement_failure_count should be 20 (all blocked), got {enforcement_failures}"
    )

    _record(
        "Force-local leakage",
        passed=(frontier_leakage == 0),
        actual=f"{frontier_leakage}/{len(FORCE_LOCAL_TASKS)}",
        expected="0/20 (0%)",
        detail=f"Blocked={blocked}, enforcement_failure_count={enforcement_failures}",
    )


# ==================================================================
# Test 2: FRONTIER-ONLY PATTERNS — CORRECT ESCALATION
# ==================================================================

def test_2_frontier_only_correct_escalation():
    """
    Tasks matching frontier_only_for with high confidence MUST be
    allowed to stay on frontier.
    """
    from context_engine.tier_router import enforce_tier, get_escalation_stats

    stats_before = get_escalation_stats()
    enforcement_failures_before = stats_before.get("enforcement_failure_count", 0)

    allowed = 0
    blocked = 0

    for task, conf in FRONTIER_ONLY_TASKS_HIGH_CONF:
        enforced_tier, reason = enforce_tier(task, "frontier", confidence=conf)
        if enforced_tier == "frontier":
            allowed += 1
        else:
            blocked += 1

    stats_after = get_escalation_stats()
    enforcement_failures_after = stats_after.get("enforcement_failure_count", 0)

    assert allowed == 10, (
        f"Expected 10 frontier-allowed tasks, got {allowed} (blocked={blocked})"
    )
    # enforcement_failure_count must NOT have increased — no blocked frontier attempts
    assert enforcement_failures_after == enforcement_failures_before, (
        f"enforcement_failure_count increased from {enforcement_failures_before} "
        f"to {enforcement_failures_after} — some tasks were wrongly blocked"
    )

    _record(
        "Frontier justified",
        passed=(allowed == 10 and blocked == 0),
        actual=f"{allowed}/{len(FRONTIER_ONLY_TASKS_HIGH_CONF)}",
        expected="10/10 (100%)",
        detail=f"Allowed={allowed}, Blocked={blocked}",
    )


# ==================================================================
# Test 3: LOW-CONFIDENCE FRONTIER — CORRECT BLOCKING
# ==================================================================

def test_3_low_confidence_blocking():
    """
    Tasks matching frontier_only_for with confidence <= 0.7 MUST be
    blocked and routed to local_model.
    """
    from context_engine.tier_router import enforce_tier, get_escalation_stats

    stats_before = get_escalation_stats()
    enforcement_failures_before = stats_before.get("enforcement_failure_count", 0)

    allowed = 0
    blocked = 0

    for task, conf in FRONTIER_ONLY_TASKS_LOW_CONF:
        enforced_tier, reason = enforce_tier(task, "frontier", confidence=conf)
        if enforced_tier == "frontier":
            allowed += 1
        else:
            blocked += 1

    stats_after = get_escalation_stats()
    enforcement_failures_after = stats_after.get("enforcement_failure_count", 0)

    assert blocked == len(FRONTIER_ONLY_TASKS_LOW_CONF), (
        f"Expected {len(FRONTIER_ONLY_TASKS_LOW_CONF)} blocked tasks, "
        f"got blocked={blocked}, allowed={allowed}"
    )
    assert allowed == 0, (
        f"Expected 0 allowed tasks (all should be blocked), got {allowed}"
    )
    # Each blocked frontier attempt increases enforcement_failure_count
    assert enforcement_failures_after == enforcement_failures_before + len(FRONTIER_ONLY_TASKS_LOW_CONF), (
        f"Expected enforcement_failure_count to increase by {len(FRONTIER_ONLY_TASKS_LOW_CONF)}, "
        f"from {enforcement_failures_before} to {enforcement_failures_before + len(FRONTIER_ONLY_TASKS_LOW_CONF)}, "
        f"got {enforcement_failures_after}"
    )

    _record(
        "Low-conf blocking",
        passed=(blocked == len(FRONTIER_ONLY_TASKS_LOW_CONF) and allowed == 0),
        actual=f"{blocked}/{len(FRONTIER_ONLY_TASKS_LOW_CONF)}",
        expected=f"{len(FRONTIER_ONLY_TASKS_LOW_CONF)}/{len(FRONTIER_ONLY_TASKS_LOW_CONF)} (100%)",
        detail=f"Blocked={blocked}, Allowed={allowed}",
    )


# ==================================================================
# Test 4: ESCALATION STATS ACCURACY
# ==================================================================

def test_4_escalation_stats_accuracy():
    """
    After routing 50 mixed tasks through enforce_tier, verify that
    get_escalation_stats() reports consistent numbers.

    Mix: 30 force-local, 3 frontier-only (high conf), 17 unknown deterministic.
    → frontier_escalations ≤ 5, forced_local ≥ 30.
    """
    from context_engine.tier_router import enforce_tier, get_escalation_stats

    mix: List[Tuple[str, str, float]] = []

    # 30 force-local — blocked from frontier
    for i in range(30):
        t = FORCE_LOCAL_TASKS[i % len(FORCE_LOCAL_TASKS)]
        mix.append((t, "frontier", 0.9))

    # 3 frontier-only (high conf) — allowed
    for i in range(3):
        t, conf = FRONTIER_ONLY_TASKS_HIGH_CONF[i % len(FRONTIER_ONLY_TASKS_HIGH_CONF)]
        mix.append((t, "frontier", conf))

    # 17 unknown deterministic — 0 frontier
    for _ in range(17):
        mix.append(("format source files", "deterministic", 0.05))

    for task, rec, conf in mix:
        enforce_tier(task, rec, confidence=conf)

    stats = get_escalation_stats()

    total = stats["total_tasks"]
    frontier_esc = stats["frontier_escalations"]
    forced_local = stats["forced_local_count"]
    det_count = stats["deterministic_tasks"]
    local_count = stats["local_model_tasks"]
    enf_fail = stats.get("enforcement_failure_count", 0)

    assert total == 50, f"Expected 50 total tasks, got {total}"
    assert forced_local >= 30, (
        f"Expected forced_local >= 30, got {forced_local}"
    )
    assert frontier_esc <= 5, (
        f"Expected frontier_escalations <= 5, got {frontier_esc}"
    )
    assert enf_fail >= 30, (
        f"Expected enforcement_failure_count >= 30, got {enf_fail}"
    )
    assert det_count >= 17, (
        f"Expected deterministic_tasks >= 17, got {det_count}"
    )

    _record(
        "Escalation stats accuracy",
        passed=(total == 50 and forced_local >= 30 and frontier_esc <= 5),
        actual=f"total={total}, frontier={frontier_esc}, forced_local={forced_local}",
        expected="total=50, frontier≤5, forced_local≥30",
        detail=f"det={det_count}, local={local_count}, enf_fail={enf_fail}",
    )


# ==================================================================
# Test 5: FRONTIER RATIO UNDER POLICY LIMIT
# ==================================================================

def test_5_frontier_ratio_under_limit():
    """
    Mix 100 tasks such that the combined enforcement converges
    the frontier ratio to ≤ TIER_POLICY['max_frontier_ratio'] (5%).

    Composition: 92 force-local, 3 frontier-only (high conf), 5 unknown.
    Force-local tasks are always blocked; frontier-only (high conf) are
    always allowed. Result: ~3-5% frontier, converging under the 5% limit.
    """
    from context_engine.tier_router import enforce_tier, TIER_POLICY, get_escalation_stats

    policy_limit = TIER_POLICY["max_frontier_ratio"]  # 0.05

    batch: List[Tuple[str, str, float]] = []

    # 92 force-local → 0 frontier (all blocked)
    for i in range(92):
        t = FORCE_LOCAL_TASKS[i % len(FORCE_LOCAL_TASKS)]
        batch.append((t, "frontier", 0.9))

    # 3 frontier-only (high conf) → allowed (must be true frontiers)
    for i in range(3):
        t, conf = FRONTIER_ONLY_TASKS_HIGH_CONF[i % len(FRONTIER_ONLY_TASKS_HIGH_CONF)]
        batch.append((t, "frontier", conf))

    # 5 unknown deterministic → 0 frontier
    for _ in range(5):
        batch.append(("format source files", "deterministic", 0.05))

    for task, rec, conf in batch:
        enforce_tier(task, rec, confidence=conf)

    stats = get_escalation_stats()
    total = stats["total_tasks"]
    frontier_uses = stats["frontier_escalations"]
    frontier_ratio = frontier_uses / max(total, 1)

    assert total == 100, f"Expected 100 total tasks, got {total}"
    assert frontier_ratio <= policy_limit, (
        f"Frontier ratio {frontier_ratio:.4f} ({frontier_uses}/{total}) "
        f"exceeds policy limit {policy_limit}"
    )

    _record(
        "Frontier ratio",
        passed=(frontier_ratio <= policy_limit),
        actual=f"{frontier_ratio*100:.1f}% ({frontier_uses}/{total})",
        expected=f"≤ {policy_limit*100:.0f}%",
        detail=f"Frontier uses={frontier_uses}, total={total}",
    )


# ==================================================================
# Test 6: LOCAL-ONLY WORKFLOW — 0 FRONTIER
# ==================================================================

def test_6_local_only_workflow_zero_frontier():
    """
    A workflow composed entirely of deterministic + local_model phases
    must produce exactly 0 frontier calls.
    """
    from context_engine.workflow_engine import WorkflowEngine, PhaseKind, PhaseResult

    engine = WorkflowEngine(Path.cwd())

    # A workflow with NO frontier phases — only deterministic + local_model
    local_only_wf_def = {
        "name": "Local Only Test",
        "description": "Deterministic + local_model only — zero frontier",
        "version": "1.0",
        "phases": [
            {
                "name": "phase_1_summarize",
                "kind": "deterministic",
                "uses": ["context.summarize"],
            },
            {
                "name": "phase_2_local",
                "kind": "local_model",
                "model": "qwen3.5:4b-16k",
                "prompt_template": "Summarize the following: {target}",
            },
            {
                "name": "phase_3_trace",
                "kind": "deterministic",
                "uses": ["graph.trace_callers"],
            },
            {
                "name": "phase_4_local_again",
                "kind": "local_model",
                "model": "qwen3.5:4b-16k",
                "prompt_template": "Generate impact summary for {target}",
            },
        ],
    }

    # Mock _call_ollama to return success immediately (avoids hanging on missing ollama)
    mock_local = PhaseResult(
        phase="", kind=PhaseKind.LOCAL_MODEL, success=True,
        output={"mock_response": "ok"}, tokens_used=10,
    )

    with patch.object(engine, "load_workflow", return_value=local_only_wf_def), \
         patch.object(engine, "_call_ollama", return_value=mock_local):
        result = engine.run("local_only_test", {"target": "test_module"})

    # Count how many phases were actually frontier
    frontier_phase_count = sum(
        1 for p in result.phases if p.kind == PhaseKind.FRONTIER
    )

    # _call_frontier emits FRONTIER_INVOKED events — check event bus too
    from context_engine.event_bus import get_event_bus
    events = get_event_bus().get_events(event_type="frontier.invoked")

    assert frontier_phase_count == 0, (
        f"Expected 0 frontier phases, got {frontier_phase_count}: "
        f"{[p.phase for p in result.phases if p.kind == PhaseKind.FRONTIER]}"
    )
    # Even error scenarios in local_model phases should NOT trigger frontier
    assert len(events) == 0, (
        f"Expected 0 FRONTIER_INVOKED events, got {len(events)} — "
        f"frontier was invoked despite local-only workflow"
    )

    # ai_calls should reflect only local_model invocations
    assert result.ai_calls == 2, (
        f"Expected 2 AI calls (both local_model), got {result.ai_calls}"
    )

    _record(
        "Local-only workflow",
        passed=(frontier_phase_count == 0 and len(events) == 0),
        actual=f"{frontier_phase_count} frontier phases, {len(events)} FRONTIER_INVOKED events",
        expected="0 frontier phases, 0 FRONTIER_INVOKED events",
        detail=f"ai_calls={result.ai_calls}, phases={len(result.phases)}, success={result.success}",
    )


# ==================================================================
# Test 7: REVERSE AUDIT — EVENT CONSISTENCY
# ==================================================================

def test_7_reverse_audit_event_consistency():
    """
    Every FRONTIER_ESCALATION event must have a corresponding
    TIER_SELECTED event, and no false escalation alarms should exist.
    """
    from context_engine.tier_router import enforce_tier
    from context_engine.event_bus import get_event_bus, FRONTIER_ESCALATION, TIER_SELECTED

    # Route a diverse set of tasks to generate events
    for task in FORCE_LOCAL_TASKS[:10]:
        enforce_tier(task, "frontier", confidence=0.9)

    for task, conf in FRONTIER_ONLY_TASKS_HIGH_CONF[:5]:
        enforce_tier(task, "frontier", confidence=conf)

    for task, conf in FRONTIER_ONLY_TASKS_LOW_CONF:
        enforce_tier(task, "frontier", confidence=conf)

    # Query events
    bus = get_event_bus()
    tier_events = bus.get_events(event_type=TIER_SELECTED, limit=200)
    escalation_events = bus.get_events(event_type=FRONTIER_ESCALATION, limit=200)

    # ── Assertion 1: Every FRONTIER_ESCALATION has a TIER_SELECTED event ──
    # Build a set of task fingerprints from TIER_SELECTED events that are frontier
    frontier_tier_tasks = set()
    for ev in tier_events:
        data = json.loads(ev["data_json"])
        if data.get("tier") == "frontier":
            # Use task prefix as fingerprint (first 100 chars to avoid truncation issues)
            frontier_tier_tasks.add(data.get("task", "")[:100])

    # Check each escalation event has a matching tier_selected event
    false_alarms = 0
    for ev in escalation_events:
        data = json.loads(ev["data_json"])
        task_fp = data.get("task", "")[:100]
        if task_fp not in frontier_tier_tasks:
            false_alarms += 1

    # ── Assertion 2: No FRONTIER_ESCALATION event should reference a
    # task that was actually routed to local_model ──
    local_tier_tasks = set()
    for ev in tier_events:
        data = json.loads(ev["data_json"])
        if data.get("tier") == "local_model":
            local_tier_tasks.add(data.get("task", "")[:100])

    local_escalation_mismatch = 0
    for ev in escalation_events:
        data = json.loads(ev["data_json"])
        task_fp = data.get("task", "")[:100]
        if task_fp in local_tier_tasks:
            local_escalation_mismatch += 1

    assert false_alarms == 0, (
        f"Found {false_alarms} FRONTIER_ESCALATION events with no matching TIER_SELECTED frontier event"
    )
    assert local_escalation_mismatch == 0, (
        f"Found {local_escalation_mismatch} escalation events for tasks actually routed to local_model"
    )

    _record(
        "Event audit",
        passed=(false_alarms == 0 and local_escalation_mismatch == 0),
        actual=f"{false_alarms} false alarms, {local_escalation_mismatch} mismatches",
        expected="0 false alarms, 0 mismatches",
        detail=f"TIER_SELECTED={len(tier_events)}, FRONTIER_ESCALATION={len(escalation_events)}",
    )


# ==================================================================
# Report generation
# ==================================================================

@pytest.fixture(scope="session", autouse=True)
def _generate_report():
    """Generate the TIER CONVERGENCE REPORT after all tests run."""
    yield  # all tests execute here

    # Count metrics (collected via _record during tests)
    total_checks = len(_convergence_metrics)
    passed_checks = sum(1 for m in _convergence_metrics if m.passed)

    # Build report lines
    lines = [
        "\n",
        "=" * 59,
        "  Tier Convergence Benchmark",
        "=" * 59,
    ]

    # Map metric names to display lines
    display_map: Dict[str, str] = {}
    for m in _convergence_metrics:
        display = "❌" if not m.passed else "✅"
        display_map[m.name] = (
            f"  {m.name:<30} {str(m.actual):>20} {display}"
        )

    # Ordered display
    order = [
        "Force-local leakage",
        "Frontier justified",
        "Low-conf blocking",
        "Frontier ratio",
        "Local-only workflow",
        "Event audit",
    ]

    for key in order:
        if key in display_map:
            lines.append(display_map[key])

    lines.append("=" * 59)

    # ── Verdict ──
    all_passed = total_checks > 0 and passed_checks == total_checks
    verdict = (
        "  Verdict: TIER CONVERGENCE ACHIEVED"
        if all_passed else
        f"  Verdict: {total_checks - passed_checks} CHECK(S) FAILED"
    )
    lines.append(verdict)
    lines.append("=" * 59)
    lines.append("")  # trailing newline

    report = "\n".join(lines)
    print(report, file=sys.stderr)  # stderr to avoid pytest swallowing

    # Also save to file
    report_path = PROJECT_ROOT / "tests" / "adversarial" / "tier_convergence_report.txt"
    report_path.write_text(report)
