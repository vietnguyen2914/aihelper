"""Daemon/MCP handler functions for knowledge operations."""
from pathlib import Path
from typing import Any, Dict
from .decisions import add_decision
from .debugging import add_debug_entry
from .preferences import set_preference
from .search import search_knowledge, get_all_knowledge

def _root(params): return Path(params["project_root"]) if params.get("project_root") else None

def handle_knowledge_add_decision(params: Dict[str, Any]) -> Dict[str, Any]:
    return add_decision(
        decision_id=params.get("id", ""), choice=params.get("choice", ""),
        reason=params.get("reason", ""), alternatives=params.get("alternatives"),
        related_files=params.get("files") or params.get("related_files"),
        confidence=params.get("confidence", 0.5), source=params.get("source", "manual"),
        tags=params.get("tags"), project_root=_root(params))

def handle_knowledge_add_debug(params: Dict[str, Any]) -> Dict[str, Any]:
    return add_debug_entry(
        symptom=params.get("symptom", ""), root_cause=params.get("root_cause", ""),
        fix_commit=params.get("fix_commit", ""), affected_modules=params.get("affected_modules"),
        error_signature=params.get("error_signature", ""), resolution=params.get("resolution", ""),
        confidence=params.get("confidence", 0.5), source=params.get("source", "manual"),
        project_root=_root(params))

def handle_knowledge_set_preference(params: Dict[str, Any]) -> Dict[str, Any]:
    return set_preference(
        key=params.get("key", ""), value=params.get("value", ""),
        category=params.get("category", ""), confidence=params.get("confidence", 0.5),
        source=params.get("source", "manual"), project_root=_root(params))

def handle_knowledge_recall(params: Dict[str, Any]) -> Dict[str, Any]:
    q = params.get("query", "")
    if q: return search_knowledge(q, _root(params), limit=params.get("limit", 10))
    return get_all_knowledge(_root(params), params.get("max_decisions", 10), params.get("max_debugs", 10))

def handle_knowledge_dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    from context_engine.knowledge_dispatcher import dispatch_knowledge
    return dispatch_knowledge(project_root=_root(params))
