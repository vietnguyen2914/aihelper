"""Developer preferences — evidence-backed key-value store."""
from pathlib import Path
from typing import Any, Dict, List, Optional
from .storage import get_db
from .evidence import escalate, log_conflict, now_iso

def set_preference(key: str, value: str, category: str = "",
                   confidence: float = 0.5, source: str = "manual",
                   project_root: Optional[Path] = None) -> Dict[str, Any]:
    db = get_db(project_root); now = now_iso()
    ex = db.execute("SELECT value,confidence,frequency,source FROM developer_preferences WHERE key=? AND status='active'", (key,)).fetchone()
    if ex:
        if ex["value"] == value:
            nc, nf = escalate(ex["confidence"], ex["frequency"], ex["source"], confidence, source)
        else:
            db.execute("UPDATE developer_preferences SET status='superseded',updated_at=? WHERE key=?", (now, key))
            log_conflict(db, "preference", key, ex["value"], value); nc, nf = confidence, 1
    else:
        nc, nf = confidence, 1
    db.execute("INSERT OR REPLACE INTO developer_preferences(key,value,category,confidence,source,frequency,last_seen,status,updated_at) VALUES(?,?,?,?,?,?,?,'active',?)",
        (key, value, category, nc, source, nf, now, now))
    db.commit()
    return {"key": key, "value": value, "category": category, "confidence": nc, "source": source, "frequency": nf, "updated_at": now}

def get_preference(key: str, project_root=None) -> Optional[str]:
    db = get_db(project_root)
    row = db.execute("SELECT value FROM developer_preferences WHERE key=? AND status='active'", (key,)).fetchone()
    return row["value"] if row else None

def list_preferences(project_root=None, category="") -> Dict[str, str]:
    db = get_db(project_root)
    if category:
        rows = db.execute("SELECT key,value FROM developer_preferences WHERE status='active' AND category=? ORDER BY key", (category,))
    else:
        rows = db.execute("SELECT key,value FROM developer_preferences WHERE status='active' ORDER BY key")
    return {r["key"]: r["value"] for r in rows}

def all_preferences_detail(project_root=None) -> List[Dict[str, Any]]:
    db = get_db(project_root)
    return [dict(r) for r in db.execute("SELECT * FROM developer_preferences WHERE status='active' ORDER BY category,key")]
