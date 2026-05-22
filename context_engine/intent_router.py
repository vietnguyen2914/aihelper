"""
Intent-aware Routing — route by coding intent, not just file/symbol.

Intent types and their context strategies:
- bugfix:       focus on error traces, recent changes, tests
- refactor:     focus on dependency graph, callers, interface boundaries
- optimization: focus on hot paths, profiling data, algorithm complexity
- schema_migration: focus on DB schema, migrations, ORM models
- ui_tweak:     focus on component tree, styles, layout files
- feature_add:  focus on existing patterns, similar features, API contracts
- investigate:  focus on symbol graph, documentation, related code

Each intent gets a tailored context strategy for maximum token efficiency.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ── Intent Detection ─────────────────────────────────────────────

INTENT_PATTERNS = [
    ("bugfix", [
        r"\bfix\b", r"\bbug\b", r"\berror\b", r"\bcrash\b", r"\bnull\b",
        r"\bexception\b", r"\bfail", r"\bwrong\b", r"\bincorrect\b",
        r"\bdoesn't work\b", r"\bnot working\b", r"\b500\b", r"\b404\b",
    ]),
    ("refactor", [
        r"\brefactor\b", r"\brename\b", r"\bextract\b", r"\bmove\b",
        r"\breorganize\b", r"\bclean\s*up\b", r"\bsplit\b", r"\bmerge\b",
        r"\bconsolidate\b", r"\bdecouple\b", r"\bdry\b",
    ]),
    ("optimization", [
        r"\boptimize\b", r"\bperformance\b", r"\bslow\b", r"\bfast",
        r"\bcache\b", r"\blazy\b", r"\bmemoize\b", r"\bindex\b",
        r"\bbottleneck\b", r"\bprofile\b", r"\bspeed\b",
    ]),
    ("schema_migration", [
        r"\bmigration\b", r"\bschema\b", r"\btable\b", r"\bcolumn\b",
        r"\badd field\b", r"\bremove field\b", r"\balter\b", r"\bdatabase\b",
        r"\bddl\b", r"\bforeign key\b", r"\bindex\b", r"\bmigrate\b",
    ]),
    ("ui_tweak", [
        r"\bui\b", r"\bstyle\b", r"\bcss\b", r"\blayout\b", r"\bcomponent\b",
        r"\bfrontend\b", r"\bhtml\b", r"\btemplate\b", r"\bview\b",
        r"\bresponsive\b", r"\balignment\b", r"\bspacing\b",
    ]),
    ("feature_add", [
        r"\badd\b", r"\bcreate\b", r"\bimplement\b", r"\bbuild\b",
        r"\bnew feature\b", r"\bscaffold\b", r"\bgenerate\b", r"\bendpoint\b",
        r"\bapi\b", r"\bcontroller\b", r"\bservice\b",
    ]),
    ("investigate", [
        r"\bhow\b", r"\bwhat\b", r"\bwhy\b", r"\bwhere\b", r"\bexplain\b",
        r"\bunderstand\b", r"\btrace\b", r"\bflow\b", r"\barchitecture\b",
        r"\bdocument\b", r"\bfind\b", r"\blocate\b", r"\bsearch\b",
    ]),
]


def detect_intent(task_description: str) -> Tuple[str, float, List[str]]:
    """Detect coding intent from task description.
    
    Returns: (intent_name, confidence, matched_keywords)
    """
    scores: Dict[str, float] = {}
    all_matches: Dict[str, List[str]] = {}

    task_lower = task_description.lower()

    for intent, patterns in INTENT_PATTERNS:
        matches = []
        for pattern in patterns:
            if re.search(pattern, task_lower):
                matches.append(pattern.replace(r"\b", ""))
        if matches:
            scores[intent] = len(matches) / len(patterns)
            all_matches[intent] = matches

    if not scores:
        return ("feature_add", 0.3, ["default"])

    best = max(scores, key=scores.get)
    return (best, scores[best], all_matches[best])


# ── Context Strategy per Intent ──────────────────────────────────

INTENT_CONTEXT_STRATEGIES = {
    "bugfix": {
        "priority": ["error_traces", "recent_changes", "test_files", "symbol_context"],
        "max_symbols": 15,
        "include_tests": True,
        "include_recent_edits": True,
        "focus_depth": 3,  # Deep focus on affected area
    },
    "refactor": {
        "priority": ["dependency_graph", "callers", "interface_boundaries", "symbol_context"],
        "max_symbols": 30,
        "include_tests": True,
        "include_recent_edits": False,
        "focus_depth": 5,  # Wide focus across modules
    },
    "optimization": {
        "priority": ["hot_paths", "profiling_data", "algorithm_context", "symbol_context"],
        "max_symbols": 10,
        "include_tests": True,
        "include_recent_edits": False,
        "focus_depth": 2,
    },
    "schema_migration": {
        "priority": ["db_schema", "migrations", "orm_models", "related_tables"],
        "max_symbols": 20,
        "include_tests": False,
        "include_recent_edits": False,
        "focus_depth": 4,
    },
    "ui_tweak": {
        "priority": ["component_tree", "styles", "layout", "template_files"],
        "max_symbols": 10,
        "include_tests": False,
        "include_recent_edits": True,
        "focus_depth": 2,
    },
    "feature_add": {
        "priority": ["existing_patterns", "similar_features", "api_contracts", "symbol_context"],
        "max_symbols": 25,
        "include_tests": True,
        "include_recent_edits": False,
        "focus_depth": 3,
    },
    "investigate": {
        "priority": ["symbol_graph", "documentation", "related_code", "architecture"],
        "max_symbols": 40,
        "include_tests": False,
        "include_recent_edits": False,
        "focus_depth": 5,
    },
}


def get_context_strategy(intent: str) -> Dict[str, Any]:
    """Get context assembly strategy for a given intent."""
    return INTENT_CONTEXT_STRATEGIES.get(intent, INTENT_CONTEXT_STRATEGIES["feature_add"])


def route_with_intent(task: str, project_root: str) -> Dict[str, Any]:
    """Full intent-aware routing: detect intent → get strategy → route."""
    intent, confidence, keywords = detect_intent(task)
    strategy = get_context_strategy(intent)

    # Get base route
    try:
        from .router import route_task
    except ImportError:
        from router import route_task

    base_route = route_task(task, project_root=Path(project_root))

    return {
        "intent": intent,
        "intent_confidence": round(confidence, 2),
        "matched_keywords": keywords,
        "context_strategy": strategy,
        "base_route": base_route,
        "recommended_tools": base_route.get("recommended_next_tools", []),
        "token_budget": {
            "max_context_tokens": strategy.get("focus_depth", 3) * 2000,
            "intent_adjusted": True,
        },
    }


from pathlib import Path


# ── Daemon handler ───────────────────────────────────────────────

def handle_intent_route(params: Dict[str, Any]) -> Dict[str, Any]:
    """Intent-aware routing handler."""
    task = params.get("task", "")
    project_root = params.get("project_root", str(Path.cwd()))
    return route_with_intent(task, project_root)
