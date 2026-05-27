"""
Engineering Intelligence Layer — public API.

Import from here: from context_engine.intelligence import add_decision, ...

Modular components:
  schema    — DB schema + migration (v1→v2)  
  storage   — DB connection + basic CRUD
  evidence  — confidence scoring, escalation, contradiction detection
  decisions — architectural decisions API
  debugging — debugging history API
  preferences — developer preferences API
  search    — FTS5 + hybrid search
  graph     — graph-memory cross-reference links
  capture   — auto-capture observer for the daemon
  handlers  — daemon/MCP handler functions
"""
from .decisions import add_decision, get_decision, list_decisions, delete_decision
from .debugging import add_debug_entry, list_debugs
from .preferences import set_preference, get_preference, list_preferences, all_preferences_detail
from .search import search_knowledge, get_all_knowledge
from .graph import link_to_graph, get_graph_links
from .storage import get_db, close_all
from .evidence import score_candidate, escalate, now_iso
from .handlers import (
    handle_knowledge_add_decision,
    handle_knowledge_add_debug,
    handle_knowledge_set_preference,
    handle_knowledge_recall,
    handle_knowledge_dispatch,
)
from .capture import auto_capture, PREFERENCE_PATTERNS

__all__ = [
    "add_decision", "get_decision", "list_decisions", "delete_decision",
    "add_debug_entry", "list_debugs",
    "set_preference", "get_preference", "list_preferences", "all_preferences_detail",
    "search_knowledge", "get_all_knowledge",
    "link_to_graph", "get_graph_links",
    "get_db", "close_all",
    "score_candidate", "escalate", "now_iso",
    "handle_knowledge_add_decision", "handle_knowledge_add_debug",
    "handle_knowledge_set_preference", "handle_knowledge_recall",
    "handle_knowledge_dispatch",
    "auto_capture", "PREFERENCE_PATTERNS",
]
