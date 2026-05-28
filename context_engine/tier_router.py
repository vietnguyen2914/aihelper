"""
Tier Router — classifies tasks into the correct execution tier.

Three tiers:
  T1 — deterministic (Python executes, zero AI)
  T2 — local model (Ollama small models)
  T3 — frontier model (GPT/Claude/DeepSeek — only for high ambiguity)
"""
from __future__ import annotations

import re
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class Tier(Enum):
    DETERMINISTIC = 1
    LOCAL_MODEL = 2
    FRONTIER = 3


# ── Hard-enforced tier policy ─────────────────────────────────
# This policy controls when frontier (cloud) model is allowed.
# By default, tasks stay on local model unless explicitly justified.

TIER_POLICY: Dict[str, Any] = {
    "max_frontier_ratio": 0.05,       # Max 5% of tasks should hit frontier
    "force_local_for": [               # These task patterns MUST use local model
        "dto", "repository", "enum", "boilerplate", "crud", "route",
        "copy", "extract", "tab_component", "simple_component",
    ],
    "frontier_only_for": [             # These patterns MAY use frontier
        "refactor", "architecture", "security", "integration", "complex_logic",
        "impact_analysis", "cross_cutting",
    ],
    "cost_limit_tokens": 8000,         # Max frontier tokens per task
    "escalation_required_reason": True, # Must provide reason for frontier use
}

# ── Escalation statistics (in-memory counter) ───────────────────
_escalation_stats: Dict[str, int] = {
    "total_tasks": 0,
    "frontier_escalations": 0,
    "local_model_tasks": 0,
    "deterministic_tasks": 0,
    "forced_local_count": 0,
    "enforcement_failure_count": 0,
}


# Tasks that are ALWAYS deterministic (no AI needed)
DETERMINISTIC_PATTERNS = [
    r"\b(cache|index|build|doctor|status|telemetry|daemon)\b",
    r"\b(git|diff|log|blame|branch)\b",
    r"\b(lint|linter|format|prettier|eslint)\b",
    r"\b(graph|caller|callee|trace|impact|explore)\b",
    r"\b(symbol|symbols|find|search|locate)\b",
    r"\b(diagnostic|compiler error|linter error)\b",
    r"\b(dependency|deps|import)\b",
    r"\b(architecture check|circular dep|dead code)\b",
    r"\b(verify|validate|check)\b.*\b(?:architecture|auth|regression|dependency)\b",
    r"\b(workflow run|workflow list)\b",
]

# Tasks that need lightweight reasoning (local model sufficient)
LOCAL_MODEL_PATTERNS = [
    r"\b(classify|categorize|rank|sort)\b",
    r"\b(summarize|summary|summarization)\b",
    r"\b(small fix|minor change|typo|rename)\b",
    r"\b(generate stub|boilerplate|scaffold template)\b",
    r"\b(review|code review)\b",
    r"\b(explain|describe|what does)\b",
    r"\b(format|style|prettify)\b",
]

# Tasks that have high ambiguity — need frontier model
FRONTIER_PATTERNS = [
    r"\b(architecture|architect|system design)\b",
    r"\b(refactor\b.*\b(?:major|large|complex|entire))\b",
    r"\b(migrate|migration)\b.*\b(?:database|schema|framework)\b",
    r"\b(trade.off|tradeoff|pro.*con|evaluate)\b",
    r"\b(novel|new pattern|design pattern)\b",
    r"\b(debug.*(?:complex|hard|obscure|race condition|deadlock))\b",
    r"\b(plan|strategy|roadmap)\b.*\b(?:long.term|future)\b",
    r"\b(multi.tenant|auth.*refactor|security.*audit)\b",
]

# Ambiguity indicators that push toward higher tiers
AMBIGUITY_MARKERS = [
    r"\b(?:maybe|perhaps|possibly|might|could be|not sure)\b",
    r"\b(?:conflict|contradict|versus|vs\.|but|however)\b",
    r"\b(?:unknown|unclear|ambiguous|uncertain)\b",
    r"\b(?:depends|it depends|trade.off)\b",
]


def compute_ambiguity_score(task: str, project_root: Optional[Path] = None) -> float:
    """Score 0.0 (fully deterministic) to 1.0 (highly ambiguous)."""
    score = 0.0
    task_lower = task.lower()

    marker_matches = sum(1 for p in AMBIGUITY_MARKERS if re.search(p, task_lower))
    score += min(marker_matches * 0.15, 0.45)

    novelty_keywords = ["new", "novel", "first time", "unfamiliar", "unknown pattern"]
    if any(kw in task_lower for kw in novelty_keywords):
        score += 0.2

    if re.search(r"(?:but|however|although|despite|conflict)", task_lower):
        score += 0.15

    if len(task.split()) > 30:
        score += 0.1
    if len(task.split()) > 80:
        score += 0.1

    return min(score, 1.0)


def classify_task(task: str, project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Classify a task into the correct execution tier."""
    task_lower = task.lower()

    # Check for clear deterministic patterns first
    det_matches = [p for p in DETERMINISTIC_PATTERNS if re.search(p, task_lower)]
    if det_matches:
        return {
            "tier": "deterministic",
            "handler": "workflow_engine.run" if "workflow" in task_lower else "daemon_handler",
            "matched_patterns": [p.replace(r"\b", "")[:40] for p in det_matches],
            "ambiguity_score": 0.0,
            "reason": "Task matches deterministic patterns",
        }

    # Check for frontier patterns (takes priority over local)
    frontier_matches = [p for p in FRONTIER_PATTERNS if re.search(p, task_lower)]
    if frontier_matches:
        score = compute_ambiguity_score(task, project_root) + 0.3
        return {
            "tier": "frontier",
            "handler": "escalate_to_frontier",
            "model": "auto",
            "matched_patterns": [p.replace(r"\b", "")[:40] for p in frontier_matches],
            "ambiguity_score": round(min(score, 1.0), 2),
            "reason": "Task requires strategic reasoning under uncertainty",
        }

    # Check for local model patterns
    local_matches = [p for p in LOCAL_MODEL_PATTERNS if re.search(p, task_lower)]
    if local_matches:
        score = compute_ambiguity_score(task, project_root)
        return {
            "tier": "local_model",
            "handler": "ollama.run",
            "model": "qwen3.5:4b-16k",
            "matched_patterns": [p.replace(r"\b", "")[:40] for p in local_matches],
            "ambiguity_score": round(score, 2),
            "reason": "Lightweight reasoning — local model sufficient",
        }

    # Default: use ambiguity score to decide
    score = compute_ambiguity_score(task, project_root)
    if score < 0.3:
        return {
            "tier": "deterministic", "handler": "daemon_handler",
            "ambiguity_score": round(score, 2),
            "reason": "Low ambiguity — execute directly",
        }
    elif score < 0.6:
        return {
            "tier": "local_model", "handler": "ollama.run",
            "model": "qwen3.5:4b-16k", "ambiguity_score": round(score, 2),
            "reason": "Moderate ambiguity — local model appropriate",
        }
    else:
        return {
            "tier": "frontier", "handler": "escalate_to_frontier",
            "ambiguity_score": round(score, 2),
            "reason": "High ambiguity — escalate to frontier model",
        }


# ── Hard-enforced tier routing ──────────────────────────────────

def should_escalate_to_frontier(task: str, confidence: float = 0.0) -> Tuple[bool, str]:
    """Determine whether a task is allowed to use frontier (cloud) model.

    Returns (should_escalate, reason_string) where:
        should_escalate=True  → task is justified for frontier use
        should_escalate=False → task MUST stay on local model
    """
    task_lower = task.lower()

    # Check forced-local patterns first (these ALWAYS override)
    for pattern in TIER_POLICY["force_local_for"]:
        if pattern in task_lower:
            return (False, f"forced_local: matches '{pattern}'")

    # Check frontier-allowed patterns
    for pattern in TIER_POLICY["frontier_only_for"]:
        if pattern in task_lower:
            if confidence > 0.7:
                return (True, f"frontier_justified: pattern '{pattern}' with confidence {confidence:.2f}")
            else:
                return (False, f"default_to_local: pattern '{pattern}' found but confidence {confidence:.2f} <= 0.7")

    return (False, "default_to_local: insufficient justification")


def enforce_tier(task: str, recommended_tier: str, confidence: float = 0.0) -> Tuple[str, str]:
    """Apply hard enforcement on the recommended tier.

    Args:
        task: The raw task description.
        recommended_tier: The tier recommended by classify_task
            ("deterministic", "local_model", "frontier").
        confidence: Ambiguity or confidence score (0.0-1.0).

    Returns:
        (enforced_tier, escalation_reason):
            enforced_tier is one of "deterministic", "local_model", "frontier"
    """
    task_lower = task.lower()

    # ── Task references a deterministic tool by name → stay deterministic ──
    det_refs = ["cache", "index", "build", "doctor", "status", "telemetry", "daemon",
                "git", "diff", "log", "blame", "branch",
                "lint", "format", "prettier", "eslint",
                "graph", "caller", "callee", "trace", "impact", "explore",
                "symbol", "find", "search", "locate",
                "diagnostic", "verify", "validate", "check",
                "workflow run", "workflow list"]
    is_deterministic_ref = any(ref in task_lower for ref in det_refs)

    # ── Check escalation policy ──
    should_escalate, reason = should_escalate_to_frontier(task, confidence)

    # ── Runtime event helper ──
    def _emit_tier_event(enforced_tier: str, escalation_reason: str) -> None:
        try:
            from .event_bus import get_event_bus, TIER_SELECTED, FRONTIER_ESCALATION
            bus = get_event_bus()
            bus.emit(TIER_SELECTED, {
                "task": task[:200],
                "tier": enforced_tier,
                "model": "auto" if enforced_tier == "frontier" else (
                    "qwen3.5:4b-16k" if enforced_tier == "local_model" else None
                ),
                "reason": escalation_reason,
            })
            if enforced_tier == "frontier":
                bus.emit(FRONTIER_ESCALATION, {
                    "task": task[:200],
                    "expected_tier": recommended_tier,
                    "reason": escalation_reason,
                })
        except Exception:
            pass

    if recommended_tier == "frontier":
        if should_escalate:
            # Allowed: frontier is justified
            _escalation_stats["frontier_escalations"] += 1
            _escalation_stats["total_tasks"] += 1
            logger.debug("Frontier escalation allowed: %s", reason)
            _emit_tier_event("frontier", reason)
            return ("frontier", reason)
        else:
            # Blocked: forced back to local_model
            _escalation_stats["forced_local_count"] += 1
            _escalation_stats["enforcement_failure_count"] += 1
            _escalation_stats["total_tasks"] += 1
            logger.info("Frontier downgraded to local_model: %s", reason)
            _emit_tier_event("local_model", reason)
            return ("local_model", reason)

    elif recommended_tier == "local_model":
        if should_escalate and not is_deterministic_ref:
            # Allow escalation to frontier when genuinely needed
            _escalation_stats["frontier_escalations"] += 1
            _escalation_stats["total_tasks"] += 1
            logger.debug("Escalated local_model to frontier: %s", reason)
            _emit_tier_event("frontier", reason)
            return ("frontier", reason)
        else:
            _escalation_stats["local_model_tasks"] += 1
            _escalation_stats["total_tasks"] += 1
            _emit_tier_event(recommended_tier, reason)
            return ("local_model", reason)

    else:  # deterministic
        _escalation_stats["deterministic_tasks"] += 1
        _escalation_stats["total_tasks"] += 1
        _emit_tier_event("deterministic", "deterministic: no AI needed")
        return ("deterministic", "deterministic: no AI needed")


def get_escalation_stats() -> Dict[str, int]:
    """Return current escalation statistics from the in-memory counter.

    Returns a copy so callers see a consistent snapshot.
    """
    return dict(_escalation_stats)


def route_tier(task: str, project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Classify a task and hard-enforce the tier policy.

    This is the preferred entry point for tier routing — it wraps
    classify_task() with enforcement, guaranteeing frontier minimization.
    """
    result = classify_task(task, project_root)
    recommended_tier = result.get("tier", "local_model")
    confidence = result.get("ambiguity_score", 0.0)

    enforced_tier, escalation_reason = enforce_tier(task, recommended_tier, confidence)
    result["enforced_tier"] = enforced_tier
    result["escalation_reason"] = escalation_reason

    return result


# ── Daemon handler ──────────────────────────────────────────────

def handle_tier_route(params: Dict[str, Any]) -> Dict[str, Any]:
    """Classify and route a task with hard enforcement."""
    task = params.get("task", "")
    project_root = Path(params.get("project_root", str(Path.cwd())))
    return route_tier(task, project_root)
