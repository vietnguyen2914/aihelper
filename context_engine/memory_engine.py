"""
Backward-compatible re-exports from the modular intelligence/ package.
All previous imports continue to work unchanged.
"""
from context_engine.intelligence import (
    add_decision, get_decision, list_decisions, delete_decision,
    add_debug_entry, list_debugs,
    set_preference, get_preference, list_preferences, all_preferences_detail,
    search_knowledge, get_all_knowledge,
    link_to_graph as link_memory_to_graph, get_graph_links,
    get_db as get_memory_db, close_all,
    score_candidate as _score_candidate,
    escalate as _escalate_confidence,
    handle_knowledge_add_decision, handle_knowledge_add_debug,
    handle_knowledge_set_preference, handle_knowledge_recall,
    handle_knowledge_dispatch,
)

# Compat stubs for old module-level names
from pathlib import Path
MEMORY_ROOT = Path.home() / ".aihelper" / "memory"
from context_engine.intelligence.evidence import now_iso as _now, log_conflict as _mark_contradiction
_row_to_dict = lambda row: dict(row)
add_session_insight = lambda *a, **kw: {"id": 0, "ok": True}
_init_schema = lambda c: None
_ensure_fts_triggers = lambda c: None
_migrate_v1_to_v2 = lambda c: None
_db_path = lambda pr: Path.home() / ".aihelper" / "memory" / "global.db"
_project_key = lambda pr: "global"

__all__ = [
    "add_decision", "get_decision", "list_decisions", "delete_decision",
    "add_debug_entry", "list_debugs",
    "set_preference", "get_preference", "list_preferences", "all_preferences_detail",
    "search_knowledge", "get_all_knowledge",
    "link_memory_to_graph", "get_graph_links",
    "get_memory_db", "close_all",
    "_score_candidate", "_escalate_confidence",
    "handle_knowledge_add_decision", "handle_knowledge_add_debug",
    "handle_knowledge_set_preference", "handle_knowledge_recall",
    "handle_knowledge_dispatch",
    "MEMORY_ROOT", "_now", "_mark_contradiction",
]
