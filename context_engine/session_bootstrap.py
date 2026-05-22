"""
Session Bootstrap — auto-hydrate context on daemon/agent startup.

On session start:
1. Recall working memory from previous sessions
2. Load scheduler state (hot files, symbols, recent errors)
3. Restore branch-specific context
4. Pre-load recent intent state
5. Return a comprehensive "session context" for AI agents

This eliminates the "cold start" problem in every AI session.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def bootstrap_session(project_root: Path) -> Dict[str, Any]:
    """
    Bootstrap a new AI session with all available context.
    Call this at the start of any AI agent session.
    """
    project_root = project_root.resolve()

    context: Dict[str, Any] = {
        "project": str(project_root),
        "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
    }

    # ── 1. Working memory ───────────────────────────────────────
    try:
        from .working_memory import recall
    except ImportError:
        from working_memory import recall

    recent_memories = recall(project_root, "", limit=10)
    if isinstance(recent_memories, dict) and recent_memories.get("items"):
        context["recent_memories"] = recent_memories["items"][:5]
    else:
        context["recent_memories"] = []

    # ── 2. Scheduler state ──────────────────────────────────────
    try:
        from .scheduler import get_scheduler
        s = get_scheduler()
        context["hot_files"] = s.get_hot_files(5)
        context["hot_symbols"] = s.get_hot_symbols(5)
        context["unstable_modules"] = s.get_unstable_modules(3)
        context["recent_errors"] = s.get_recent_errors(str(project_root))
        predictions = s.predict_next_actions()
        context["predicted_actions"] = predictions[:3] if predictions else []
    except Exception:
        context["scheduler_unavailable"] = True

    # ── 3. Branch context ───────────────────────────────────────
    try:
        from .auto_apply import recall_branch_context, _get_branch
        branch = _get_branch(project_root)
        branch_ctx = recall_branch_context(project_root, branch)
        if branch_ctx.get("context"):
            context["branch"] = branch
            context["branch_context"] = branch_ctx["context"]
    except Exception:
        pass

    # ── 4. Intent state ─────────────────────────────────────────
    try:
        from .auto_apply import get_intent_state
        intent = get_intent_state(project_root)
        if intent.get("current_intent"):
            context["previous_intent"] = intent["current_intent"]
            context["intent_history"] = intent.get("history", [])[-3:]
    except Exception:
        pass

    # ── 5. Git context ──────────────────────────────────────────
    try:
        result = subprocess.run(
            ["git", "--no-pager", "log", "--oneline", "-5"],
            cwd=str(project_root),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        if result.returncode == 0:
            context["recent_commits"] = result.stdout.strip().split("\n")
    except Exception:
        pass

    # ── 6. Editor context ───────────────────────────────────────
    try:
        from .editor_context import get_editor_context
        editor = get_editor_context(project_root)
        context["editor"] = editor
    except Exception:
        pass

    # ── 7. Cache freshness ──────────────────────────────────────
    try:
        from .cache import cache_status
        status = cache_status(project_root)
        context["cache"] = {
            "fresh": status.get("fresh", False),
            "files": status.get("manifest", {}).get("file_count", 0),
            "symbols": status.get("manifest", {}).get("symbol_count", 0),
        }
    except Exception:
        pass

    return context


# ── Daemon handler ───────────────────────────────────────────────

def handle_bootstrap(params: Dict[str, Any]) -> Dict[str, Any]:
    """Bootstrap session context."""
    project_root = Path(params.get("project_root", str(Path.cwd())))
    return bootstrap_session(project_root)
