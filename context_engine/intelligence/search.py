"""Hybrid search: FTS5 full-text + LIKE fallback across all knowledge types."""
from pathlib import Path
from typing import Any, Dict, Optional
from .storage import get_db
from .decisions import list_decisions
from .debugging import list_debugs
from .preferences import list_preferences

def search_knowledge(query: str, project_root: Optional[Path] = None,
                     limit: int = 10) -> Dict[str, Any]:
    db = get_db(project_root); st = f"%{query}%"; r = {"decisions": [], "debugs": [], "preferences": {}}
    try:
        rows = db.execute("SELECT id,choice,reason FROM decisions_fts WHERE decisions_fts MATCH ? LIMIT ?", (query, limit)).fetchall()
        if rows: r["decisions"] = [{"id": x["id"], "choice": x["choice"], "reason": (x["reason"] or "")[:200]} for x in rows]
    except Exception: pass
    if not r["decisions"]:
        rows = db.execute("SELECT id,choice,reason FROM architectural_decisions WHERE status='active' AND (choice LIKE ? OR reason LIKE ? OR alternatives LIKE ?) LIMIT ?", (st,st,st,limit))
        r["decisions"] = [{"id": x["id"], "choice": x["choice"], "reason": (x["reason"] or "")[:200]} for x in rows]
    try:
        rows = db.execute("SELECT rowid,symptom,root_cause FROM debugging_fts WHERE debugging_fts MATCH ? LIMIT ?", (query, limit)).fetchall()
        if rows: r["debugs"] = [{"id": x["rowid"], "symptom": x["symptom"][:200], "root_cause": (x["root_cause"] or "")[:200]} for x in rows]
    except Exception: pass
    if not r["debugs"]:
        rows = db.execute("SELECT id,symptom,root_cause FROM debugging_history WHERE status='active' AND (symptom LIKE ? OR root_cause LIKE ? OR resolution LIKE ?) LIMIT ?", (st,st,st,limit))
        r["debugs"] = [{"id": x["id"], "symptom": x["symptom"][:200], "root_cause": (x["root_cause"] or "")[:200]} for x in rows]
    rows = db.execute("SELECT key,value FROM developer_preferences WHERE status='active' AND (key LIKE ? OR value LIKE ? OR category LIKE ?) LIMIT ?", (st,st,st,limit))
    r["preferences"] = {x["key"]: x["value"] for x in rows}
    return r

def get_all_knowledge(project_root=None, max_decisions=10, max_debugs=10) -> Dict[str, Any]:
    return {"decisions": list_decisions(project_root, limit=max_decisions),
            "debugs": list_debugs(project_root, limit=max_debugs),
            "preferences": list_preferences(project_root)}
