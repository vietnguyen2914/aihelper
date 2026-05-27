"""Debugging history — store and query with recurrence detection."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from .storage import get_db
from .evidence import now_iso

def add_debug_entry(symptom: str, root_cause: str = "", fix_commit: str = "",
                    affected_modules: Optional[List[str]] = None,
                    error_signature: str = "", resolution: str = "",
                    confidence: float = 0.5, source: str = "manual",
                    project_root: Optional[Path] = None) -> Dict[str, Any]:
    db = get_db(project_root); now = now_iso()
    if error_signature:
        ex = db.execute("SELECT id,recurrence_count,frequency,confidence FROM debugging_history WHERE error_signature=? AND error_signature!='' AND status='active' ORDER BY id DESC LIMIT 1", (error_signature,)).fetchone()
        if ex:
            db.execute("UPDATE debugging_history SET recurrence_count=?,frequency=?,last_seen=?,confidence=MIN(confidence+0.05,0.9),resolved_at=? WHERE id=?", (ex["recurrence_count"]+1, ex["frequency"]+1, now, ex["id"]))
            db.commit()
            return {"id": ex["id"], "recurrence": True, "count": ex["recurrence_count"]+1, "confidence": min(ex["confidence"]+0.05, 0.9)}
    cursor = db.execute("INSERT INTO debugging_history(symptom,root_cause,fix_commit,affected_modules,error_signature,resolution,resolved_at,confidence,source,frequency,last_seen,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,'active',?)",
        (symptom, root_cause, fix_commit, json.dumps(affected_modules or []), error_signature, resolution, now, confidence, source, 1, now, now))
    db.commit()
    return {"id": cursor.lastrowid, "symptom": symptom, "root_cause": root_cause, "fix_commit": fix_commit, "affected_modules": affected_modules or [], "confidence": confidence, "source": source, "resolved_at": now}

def list_debugs(project_root=None, limit=20, status="active"):
    db = get_db(project_root)
    rows = db.execute("SELECT * FROM debugging_history WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit))
    return [_row_to_dict(r) for r in rows]

def _row_to_dict(row):
    r = dict(row)
    if "affected_modules" in r and isinstance(r["affected_modules"], str):
        try: r["affected_modules"] = json.loads(r["affected_modules"])
        except (json.JSONDecodeError, TypeError): pass
    return r
