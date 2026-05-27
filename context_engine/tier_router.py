"""
Tier Router — classifies tasks into the correct execution tier.

Three tiers:
  T1 — deterministic (Python executes, zero AI)
  T2 — local model (Ollama small models)
  T3 — frontier model (GPT/Claude/DeepSeek — only for high ambiguity)
"""
from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class Tier(Enum):
    DETERMINISTIC = 1
    LOCAL_MODEL = 2
    FRONTIER = 3


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


# ── Daemon handler ──────────────────────────────────────────────

def handle_tier_route(params: Dict[str, Any]) -> Dict[str, Any]:
    """Classify and route a task."""
    task = params.get("task", "")
    project_root = Path(params.get("project_root", str(Path.cwd())))
    return classify_task(task, project_root)
