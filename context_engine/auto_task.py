"""
Auto Task — unified autonomous task pipeline.

The single entry point for `aihelper task "implement X"`. Detects intent,
auto-selects workflows, compiles cognition packages, routes tiers, partitions
work, executes through the runtime, and emits telemetry — all in one call.
"""
from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Task → Workflow mapping ────────────────────────────────────

TASK_TO_WORKFLOW: Dict[str, str] = {
    "crud": "scaffold",
    "dto": "scaffold",
    "entity": "scaffold",
    "repository": "scaffold",
    "refactor": "refactor_safety",
    "architecture": "architecture_review",
    "bug": "diagnose",
    "error": "diagnose",
    "fix": "diagnose",
    "test": "tdd",
    "security": "auth_audit",
    "deploy": "release_check",
}


def auto_select_workflow(task: str) -> Optional[str]:
    """Auto-select a workflow based on task patterns.

    Matches keywords in TASK_TO_WORKFLOW against the task string
    (case-insensitive). Returns the matched workflow name or None
    if no keyword matched.
    """
    task_lower = task.lower()
    for keyword, workflow in TASK_TO_WORKFLOW.items():
        if keyword in task_lower:
            logger.debug("auto_select_workflow: '%s' matched keyword '%s' → workflow '%s'", task, keyword, workflow)
            return workflow
    logger.debug("auto_select_workflow: no workflow matched for '%s'", task)
    return None


def extract_target(task: str) -> str:
    """Extract a target symbol from the task description.

    Heuristic priority:
      1. First capitalized word in the task (likely a symbol/type name)
      2. Phrase after 'for ' — e.g. 'create DTO for User' → 'User'
      3. Fallback to the task itself (the whole task is the target)
    """
    # Priority 1: "for X" pattern
    for_match = re.search(r'\bfor\s+([A-Z]\w*)', task)
    if for_match:
        target = for_match.group(1)
        logger.debug("extract_target: 'for X' pattern → '%s'", target)
        return target

    # Priority 2: first capitalized word that isn't a common verb
    skip_words = {"I", "A", "An", "The", "We", "You", "It", "This", "That", "These", "Those"}
    for word in task.split():
        clean = word.strip(",.!?;:'\"()[]{}")
        if clean and clean[0].isupper() and clean not in skip_words and len(clean) > 1:
            logger.debug("extract_target: first capitalized word → '%s'", clean)
            return clean

    # Priority 3: prepositional phrase "to X" or "in X"
    for prep_match in re.finditer(r'\b(?:to|in|of|for)\s+([A-Za-z]\w+)', task):
        candidate = prep_match.group(1)
        if candidate[0].isupper() or candidate in ("db", "dbm", "sql"):
            logger.debug("extract_target: preposition pattern → '%s'", candidate)
            return candidate

    # Fallback: whole task as target
    logger.debug("extract_target: no pattern matched, using task as target")
    return task


def emit_task_completed(task: str, intent: Dict[str, Any], tier_result: Dict[str, Any]) -> None:
    """Emit completion telemetry to the event bus.

    Silently catches errors — telemetry is best-effort.
    """
    try:
        from .event_bus import get_event_bus

        bus = get_event_bus()
        bus.emit("task.completed", {
            "task": task[:500],
            "intent": intent.get("name", "unknown") if isinstance(intent, dict) else str(intent),
            "intent_confidence": intent.get("confidence", 0.0) if isinstance(intent, dict) else 0.0,
            "tier": tier_result.get("enforced_tier", "unknown"),
            "ambiguity": tier_result.get("ambiguity_score", 0.0),
        })
        logger.debug("emit_task_completed: emitted task.completed event")
    except Exception as exc:
        logger.debug("emit_task_completed: skipped (event bus unavailable): %s", exc)


# ── Main Pipeline ──────────────────────────────────────────────

def auto_task(task: str, project_root: Path) -> Dict[str, Any]:
    """Execute the unified autonomous task pipeline.

    Pipeline steps:
      1. Detect intent via intent_detector
      2. Auto-select workflow via auto_select_workflow
      3. Compile cognition package (call graph + compressed context + primitives)
      4. Auto tier routing with enforcement
      5. Auto partition if > 3 primitives
      6. Execute through WorkflowEngine (either named workflow or subagent)
      7. Emit completion telemetry

    Args:
        task: The task description (e.g. "add logo upload to Group")
        project_root: Absolute path to the project root.

    Returns:
        Dict with pipeline results including intent, workflow, tier,
        partitions, and runtime_owned flag.
    """
    from .intent_detector import detect_intent
    from .tier_router import route_tier
    from .subagent_wiring import compile_cognition_package
    from .partition_optimizer import optimize_partitions
    from .workflow_engine import WorkflowEngine

    logger.info("auto_task: starting pipeline for task='%s' root='%s'", task, project_root)

    # Step 1: Detect intent
    intent: Dict[str, Any] = detect_intent(task)
    logger.debug("auto_task: intent detected → %s", intent.get("name", "unknown"))

    # Step 2: Auto-select workflow
    workflow: Optional[str] = auto_select_workflow(task)
    logger.debug("auto_task: workflow selected → %s", workflow or "none (will use subagent)")

    # Step 3: Extract target and compile cognition package
    target: str = extract_target(task)
    pkg: Dict[str, Any] = compile_cognition_package(task, target, project_root)
    allowed_primitives: List[str] = pkg.get("allowed_primitives", [])
    logger.debug("auto_task: cognition package compiled (target='%s', %d primitives)", target, len(allowed_primitives))

    # Step 4: Auto tier routing
    tier_result: Dict[str, Any] = route_tier(task, project_root)
    enforced_tier: str = tier_result.get("enforced_tier", "local_model")
    logger.debug("auto_task: tier routed → %s", enforced_tier)

    # Step 5: Auto partition if needed (> 3 primitives is a heuristic for parallelism opportunity)
    partition_count: int = 1
    if len(allowed_primitives) > 3:
        try:
            partition_result = optimize_partitions(allowed_primitives, {}, project_root)
            partition_count = partition_result.partition_count
            logger.debug("auto_task: partitioned into %d partitions", partition_count)
        except Exception as exc:
            logger.warning("auto_task: partition optimization failed, continuing: %s", exc)
    else:
        logger.debug("auto_task: skipping partition optimization (%d primitives <= 3)", len(allowed_primitives))

    # Step 6: Execute through runtime
    engine = WorkflowEngine(project_root)
    if workflow:
        # Named workflow execution
        logger.info("auto_task: executing workflow '%s'", workflow)
        from dataclasses import asdict
        workflow_result = engine.run(workflow, {"task": task, "target": target})
        runtime_result = {
            "workflow_result": asdict(workflow_result) if hasattr(workflow_result, "__dataclass_fields__") else str(workflow_result),
            "workflow_success": workflow_result.success if hasattr(workflow_result, "success") else None,
        }
    else:
        # Subagent execution
        logger.info("auto_task: executing subagent (target='%s')", target)
        subagent_result = engine.run_subagent(task, target)
        runtime_result = dict(subagent_result)

    # Step 7: Emit completion telemetry
    emit_task_completed(task, intent, tier_result)

    return {
        "task": task,
        "target": target,
        "intent": intent.get("name", "unknown") if isinstance(intent, dict) else "unknown",
        "intent_detail": intent,
        "workflow": workflow,
        "tier": tier_result,
        "enforced_tier": enforced_tier,
        "partitions": partition_count,
        "primitives_count": len(allowed_primitives),
        "runtime_result": runtime_result,
        "runtime_owned": True,
    }


# ── Daemon Handler ─────────────────────────────────────────────

def handle_auto_task(params: Dict[str, Any]) -> Dict[str, Any]:
    """Daemon handler for the 'auto_task' method.

    Expected params:
        task: str — the task description
        project_root: str — absolute path to project root
    """
    task = str(params.get("task", "")).strip()
    if not task:
        return {"error": "task is required", "runtime_owned": False}

    raw_root = params.get("project_root", str(Path.cwd()))
    project_root = Path(raw_root).expanduser().resolve()

    return auto_task(task, project_root)
