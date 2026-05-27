"""Architectural decisions — CRUD with evidence tracking."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from .storage import get_db
from .evidence import escalate, log_conflict, now_iso
from .graph import link_to_graph

def add_decision(decision_id: str, choice: str, reason: str = "",
                 alternatives: Optional[List] = None,
                 related_files: Optional[List[str]] = None,
                 confidence: float = 0.5, source: str = "manual",
                 tags: Optional[List[str]] = None,
                 supersedes: str = "", status: str = "active",
                 project_root: Optional[Path] = None) -> Dict[str, Any]:
    db = get_db(project_root); now = now_iso()
    ex = db.execute("SELECT confidence,frequency,source,choice FROM architectural_decisions WHERE id=?", (decision_id,)).fetchone()
    if ex:
        if ex["choice"] == choice:
            nc, nf = escalate(ex["confidence"], ex["frequency"], ex["source"], confidence, source)
        else:
            db.execute("UPDATE architectural_decisions SET status='superseded',updated_at=? WHERE id=?", (now, decision_id))
            log_conflict(db, "decision", decision_id, ex["choice"], choice)
            decision_id = f"{decision_id}-v{int(ex['frequency'] or 1)+1}"; nc, nf = confidence, 1
    else:
        nc, nf = confidence, 1
    alts_json = json.dumps([a if isinstance(a, dict) else str(a) for a in (alternatives or [])])
    db.execute("INSERT OR REPLACE INTO architectural_decisions(id,choice,reason,alternatives,related_files,confidence,source,frequency,last_seen,status,supersedes,tags,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,COALESCE((SELECT created_at FROM architectural_decisions WHERE id=?),?),?)",
        (decision_id, choice, reason, alts_json, json.dumps(related_files or []), nc, source, nf, now, status, supersedes, json.dumps(tags or []), decision_id, now, now))
    db.commit()
    if related_files:
        for f in related_files[:10]: link_to_graph("decision", decision_id, f, "documents", project_root)
    return {"id": decision_id, "choice": choice, "reason": reason, "alternatives": alternatives or [],
            "related_files": related_files or [], "confidence": nc, "source": source, "frequency": nf,
            "status": status, "supersedes": supersedes, "tags": tags or [], "updated_at": now}

def get_decision(decision_id: str, project_root=None):
    db = get_db(project_root)
    row = db.execute("SELECT * FROM architectural_decisions WHERE id=? AND status='active'", (decision_id,)).fetchone()
    if not row: return None
    from .graph import get_graph_links
    r = _row_to_dict(row); r["graph_links"] = get_graph_links("decision", decision_id, project_root); return r

def list_decisions(project_root=None, limit=20, status="active"):
    db = get_db(project_root)
    return [_row_to_dict(r) for r in db.execute("SELECT * FROM architectural_decisions WHERE status=? ORDER BY updated_at DESC LIMIT ?", (status, limit))]

def delete_decision(decision_id, project_root=None):
    db = get_db(project_root)
    db.execute("UPDATE architectural_decisions SET status='deprecated',updated_at=? WHERE id=?", (now_iso(), decision_id))
    db.commit(); return db.total_changes > 0

def _row_to_dict(row):
    r = dict(row)
    for f in ("alternatives", "related_files", "tags"):
        if f in r and isinstance(r[f], str):
            try: r[f] = json.loads(r[f])
            except (json.JSONDecodeError, TypeError): pass
    return r
