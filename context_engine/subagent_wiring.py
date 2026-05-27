"""
Subagent Wiring — ensures spawned sub-agents receive AIHELPER cognition packages
instead of raw prompts.

When a parent agent spawns a sub-agent, this module:
  1. Compiles a distilled CognitionPackage from the aihelper graph/index
  2. Generates a structured bilingual prompt that MANDATES aihelper tool usage
  3. Enforces call-graph boundaries and tier routing for the sub-agent

Design principle: every sub-agent gets a pre-computed knowledge graph boundary
so it never needs to grep/scan the codebase. This eliminates redundant discovery
work across agents.

v0.1: Initial wiring — CognitionPackage + bilingual prompt generation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


# ── CognitionPackage dataclass ──────────────────────────────────

@dataclass
class CognitionPackage:
    """A distilled knowledge package for sub-agent consumption.

    Contains pre-computed call graph boundary, compressed context,
    tier routing recommendation, and invalidation scope — so the
    sub-agent never needs to scan/grep the codebase.
    """
    graph_boundary: Dict[str, Any] = field(default_factory=dict)
    context_package: Dict[str, Any] = field(default_factory=dict)
    tier_recommendation: str = "local_model"  # "deterministic" | "local_model" | "frontier"
    allowed_primitives: List[str] = field(default_factory=list)
    invalidation_scope: str = "symbol"
    token_budget: int = 2000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_boundary": self.graph_boundary,
            "context_package": self.context_package,
            "tier_recommendation": self.tier_recommendation,
            "allowed_primitives": self.allowed_primitives,
            "invalidation_scope": self.invalidation_scope,
            "token_budget": self.token_budget,
        }


# ── Main compilation function ───────────────────────────────────

def compile_cognition_package(
    task: str,
    target: str,
    project_root: Path,
    max_tokens: int = 2000,
) -> Dict[str, Any]:
    """Compile a CognitionPackage for a sub-agent.

    Uses the compressor to build a distilled cognition package, then
    enriches it with call-graph boundary, tier routing, primitive
    filtering, and invalidation scope.

    Args:
        task: The task description the sub-agent needs to perform.
        target: The target symbol or module to scope work to.
        project_root: Absolute path to the project root.
        max_tokens: Maximum token budget for the sub-agent.

    Returns:
        A CognitionPackage dict ready for prompt generation or direct use.
    """
    from .graph_db import get_db
    from .graph_query import _find_symbol_id
    from .compressor import compress_context
    from .tier_router import classify_task

    db = get_db(project_root)

    # ── Build graph boundary ─────────────────────────────────────
    sym_id = _find_symbol_id(target, project_root) if target else None
    callers_raw = db.get_callers(sym_id, max_depth=2) if sym_id else []
    callees_raw = db.get_callees(sym_id, max_depth=2) if sym_id else []

    graph_boundary: Dict[str, Any] = {
        "target": target,
        "callers": [c.get("name", "") for c in callers_raw[:15]],
        "callees": [c.get("name", "") for c in callees_raw[:15]],
        "max_depth": 2,
        "total_callers": len(callers_raw),
        "total_callees": len(callees_raw),
    }

    # ── Build compressed context ─────────────────────────────────
    ctx: Dict[str, Any] = {
        "question": task,
        "target": target,
    }
    if sym_id:
        ctx["symbol_id"] = sym_id
        ctx["callers"] = callers_raw
        ctx["callees"] = callees_raw

    # Pull historical knowledge
    try:
        from .intelligence.search import search_knowledge
        ctx["memories"] = search_knowledge(task or target, limit=10)
    except Exception:
        ctx["memories"] = []

    ctx["circular_deps"] = db.find_circular_deps()
    ctx["dead_code"] = db.find_dead_code()
    ctx["modules"] = {}
    ctx["hot_paths"] = []
    ctx["files"] = list({
        entry.get("file_path", "")
        for entries in [callers_raw, callees_raw]
        for entry in entries
        if isinstance(entry, dict) and entry.get("file_path")
    })[:20]

    context_package = compress_context(ctx, project_root)

    # ── Tier routing ─────────────────────────────────────────────
    tier_result = classify_task(task, project_root)
    tier_recommendation = tier_result.get("tier", "local_model")

    # ── Select relevant primitives ───────────────────────────────
    allowed_primitives = _select_primitives_for_task(task, target)

    # ── Determine invalidation scope ─────────────────────────────
    invalidation_scope = _determine_invalidation_scope(
        target, callers_raw, callees_raw, tier_recommendation
    )

    package = CognitionPackage(
        graph_boundary=graph_boundary,
        context_package=context_package,
        tier_recommendation=tier_recommendation,
        allowed_primitives=allowed_primitives,
        invalidation_scope=invalidation_scope,
        token_budget=max_tokens,
    )

    return package.to_dict()


# ── Prompt generation ───────────────────────────────────────────

def generate_subagent_prompt(cognition_package: Dict[str, Any]) -> str:
    """Generate a structured bilingual prompt that MANDATES aihelper usage.

    The prompt includes both Vietnamese and English directives so the
    sub-agent understands constraints regardless of its configured language.

    Args:
        cognition_package: A CognitionPackage dict (from to_dict()).

    Returns:
        A multi-paragraph prompt string ready to send to the sub-agent.
    """
    import json

    graph = cognition_package.get("graph_boundary", {})
    tier = cognition_package.get("tier_recommendation", "local_model")
    primitives = cognition_package.get("allowed_primitives", [])
    scope = cognition_package.get("invalidation_scope", "symbol")
    budget = cognition_package.get("token_budget", 2000)
    ctx = cognition_package.get("context_package", {})

    # ── Build model guidance ─────────────────────────────────────
    if tier == "deterministic":
        model_guidance = (
            "Sử dụng Python deterministic execution — không cần AI model.\n"
            "Use Python deterministic execution — no AI model needed."
        )
    elif tier == "frontier":
        model_guidance = (
            "Sử dụng frontier model (GPT/Claude/DeepSeek) — task có độ ambiguity cao.\n"
            "Use frontier model (GPT/Claude/DeepSeek) — high ambiguity task."
        )
    else:
        model_guidance = (
            "Sử dụng local Ollama model (qwen3.5:4b-16k) — task đơn giản.\n"
            "Use local Ollama model (qwen3.5:4b-16k) — simple task."
        )

    # ── Build primitive guidance ─────────────────────────────────
    if primitives:
        prim_list = ", ".join(primitives[:10])
        prim_guidance = (
            f"ALLOWED_PRIMITIVES: {prim_list}\n"
            f"Chỉ sử dụng các primitive được liệt kê ở trên.\n"
            f"Only use the primitives listed above."
        )
    else:
        prim_guidance = (
            "ALLOWED_PRIMITIVES: all available\n"
            "Có thể sử dụng tất cả các primitive.\n"
            "All primitives are available."
        )

    # ── Build scope guidance ─────────────────────────────────────
    scope_map = {
        "symbol": "Chỉ thay đổi symbol được chỉ định. Only modify the specified symbol.",
        "file": "Chỉ thay đổi file được chỉ định. Only modify the specified file.",
        "module": "Chỉ thay đổi trong module được chỉ định. Only modify within the specified module.",
        "global": "Toàn bộ codebase. Entire codebase is accessible.",
    }
    scope_guidance = scope_map.get(scope, scope_map["symbol"])

    # ── Assemble the prompt ──────────────────────────────────────
    prompt = f"""=== AIHELPER SUB-AGENT DIRECTIVES ===

[CONSTRAINTS — BẮT BUỘC]
1. BẮT BUỘC: Sử dụng aihelper context/symbol_lookup/callers/callees thay vì grep/scan thô.
   MANDATORY: Use aihelper context/symbol_lookup/callers/callees instead of raw grep/scan.

2. CẤM: Chạy terminal find/grep để khám phá codebase.
   FORBIDDEN: Run terminal find/grep to explore the codebase.

3. BOUNDARY: Chỉ hoạt động trong call-graph boundary được cấp.
   BOUNDARY: Only operate within the granted call-graph boundary.

4. TIER: {model_guidance}

5. SCOPE: {scope_guidance}

6. {prim_guidance}

7. TOKEN_BUDGET: {budget} tokens tối đa. TOKEN_BUDGET: {budget} tokens max.

[TASK]
{ctx.get('question', 'No task specified')}

[CALL-GRAPH BOUNDARY]
Target: {graph.get('target', 'N/A')}
Callers ({graph.get('total_callers', 0)} total): {json.dumps(graph.get('callers', []), ensure_ascii=False)}
Callees ({graph.get('total_callees', 0)} total): {json.dumps(graph.get('callees', []), ensure_ascii=False)}
Max depth: {graph.get('max_depth', 2)}

[COGNITION PACKAGE]
{json.dumps(ctx, default=str, ensure_ascii=False, indent=2)}

=== END DIRECTIVES ===
"""
    return prompt.strip()


# ── Daemon handlers ─────────────────────────────────────────────

def handle_subagent_wiring(params: Dict[str, Any]) -> Dict[str, Any]:
    """Daemon handler: compile cognition package + generate prompt.

    Expects params:
        task: str          — task description
        target: str        — target symbol/module
        project_root: str  — project root path
        max_tokens: int    — (optional) token budget, default 2000

    Returns:
        Dict with cognition_package and generated_prompt.
    """
    task = params.get("task", params.get("question", ""))
    target = params.get("target", "")
    project_root = Path(params.get("project_root", str(Path.cwd())))
    max_tokens = int(params.get("max_tokens", 2000))

    if not task:
        return {"error": "task is required for subagent_wiring"}

    cognition_package = compile_cognition_package(
        task=task,
        target=target,
        project_root=project_root,
        max_tokens=max_tokens,
    )

    generated_prompt = generate_subagent_prompt(cognition_package)

    return {
        "cognition_package": cognition_package,
        "generated_prompt": generated_prompt,
        "token_estimate": len(generated_prompt) // 4,
    }


def handle_cognition_package(params: Dict[str, Any]) -> Dict[str, Any]:
    """Lightweight daemon handler: return cognition package only (no prompt).

    Useful for parent agents that want to compose their own prompts
    on top of the pre-compiled package.

    Expects params:
        task: str          — task description
        target: str        — target symbol/module
        project_root: str  — project root path
        max_tokens: int    — (optional) token budget, default 2000

    Returns:
        Dict with cognition_package only.
    """
    task = params.get("task", params.get("question", ""))
    target = params.get("target", "")
    project_root = Path(params.get("project_root", str(Path.cwd())))
    max_tokens = int(params.get("max_tokens", 2000))

    if not task:
        return {"error": "task is required for cognition_package"}

    cognition_package = compile_cognition_package(
        task=task,
        target=target,
        project_root=project_root,
        max_tokens=max_tokens,
    )

    return {
        "cognition_package": cognition_package,
    }


# ── Internal helpers ────────────────────────────────────────────

def _select_primitives_for_task(task: str, target: str) -> List[str]:
    """Select relevant primitives based on task content.

    Maps task patterns to the primitives most useful for that work.
    Falls back to a core set of discovery primitives.
    """
    from .primitives import get_registry

    task_lower = task.lower()
    reg = get_registry()
    selected: List[str] = []

    # Always include core discovery primitives
    core = ["graph.analyze_target", "memory.recall", "context.compress"]
    for name in core:
        if name in reg:
            selected.append(name)

    # Pattern-based selection
    if any(kw in task_lower for kw in ["caller", "impact", "who uses", "affect"]):
        selected.append("graph.trace_callers")
        selected.append("graph.impact_radius")

    if any(kw in task_lower for kw in ["callee", "depend", "trace down", "call path"]):
        selected.append("graph.trace_callees")
        selected.append("graph.impact_radius")

    if any(kw in task_lower for kw in ["test", "spec", "coverage", "suite"]):
        selected.append("test.run")
        selected.append("test.generate_stub")

    if any(kw in task_lower for kw in ["refactor", "change", "modify", "update"]):
        selected.append("verify.regression_risk")

    if any(kw in task_lower for kw in ["security", "auth", "secret", "token", "password"]):
        selected.append("verify.auth_safety")

    if any(kw in task_lower for kw in [
        "architecture", "circular", "dead code", "health check"
    ]):
        selected.append("verify.architecture")
        selected.append("verify.dependency_health")

    if any(kw in task_lower for kw in ["risk", "classify", "assess", "evaluate"]):
        selected.append("risk.classify")

    if any(kw in task_lower for kw in ["git", "diff", "change", "commit"]):
        selected.append("git.diff")

    if any(kw in task_lower for kw in ["lint", "format", "style"]):
        selected.append("lint.run")

    # Deduplicate while preserving order
    seen: set = set()
    result = []
    for name in selected:
        if name not in seen:
            seen.add(name)
            result.append(name)

    return result


def _determine_invalidation_scope(
    target: str,
    callers: List[Dict[str, Any]],
    callees: List[Dict[str, Any]],
    tier: str,
) -> str:
    """Determine appropriate invalidation scope for the task.

    Conservative fallback: widens scope when confidence is low.
    Based on the ChangeClassification.invalidation_scope pattern
    from invalidation.py.

    Args:
        target: The target symbol name.
        callers: Raw caller entries from graph_db.
        callees: Raw callee entries from graph_db.
        tier: The tier recommendation ("deterministic" | "local_model" | "frontier").

    Returns:
        One of "symbol", "file", or "module".
    """
    total_callers = len(callers)
    total_callees = len(callees)

    # Few dependencies → safe to scope tightly
    if total_callers <= 3 and total_callees <= 3:
        return "symbol"

    # Frontier tasks need wider scope (high ambiguity)
    if tier == "frontier":
        return "module"

    # Moderate dependencies → file-level scope
    return "file"


# ── Registration helper for daemon.py ───────────────────────────

def register_handlers() -> Dict[str, Any]:
    """Return handler dict for registration in daemon.py's _external_handlers."""
    return {
        "subagent_wiring": handle_subagent_wiring,
        "cognition_package": handle_cognition_package,
    }
