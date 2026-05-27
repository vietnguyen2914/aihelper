"""Evidence model: confidence escalation, candidate scoring, contradiction logging."""
from datetime import datetime, timezone
from typing import Any, Dict
from .storage import get_db

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def escalate(existing_conf: float, existing_freq: int, existing_src: str,
             new_conf: float, new_src: str) -> tuple:
    freq = existing_freq + 1
    if new_src == "manual" or existing_src == "manual":
        conf = max(existing_conf, new_conf, 0.8)
        if existing_src == "manual" and new_src == "manual":
            conf = min(existing_conf + 0.1, 0.95)
    elif new_src == "auto-detected":
        conf = min(existing_conf + 0.1, 0.7)
    else:
        conf = max(existing_conf, new_conf)
    return conf, freq

def log_conflict(conn, entity_type: str, entity_key: str,
                 old_val: str, new_val: str) -> None:
    conn.execute(
        "INSERT INTO knowledge_conflicts(entity_type,entity_key,old_value,new_value,detected_at) VALUES(?,?,?,?,?)",
        (entity_type, entity_key, old_val, new_val, now_iso()))
    conn.commit()

def score_candidate(method: str, params: Dict[str, Any],
                    result: Dict[str, Any]) -> float:
    s = 0.0
    if method in ("patch_plan", "safe_apply", "confidence"): s += 0.4
    elif method == "diagnostics": s += 0.35
    elif method in ("route", "context"): s += 0.15
    elif method == "bootstrap": s += 0.3
    if params.get("files") or params.get("related_files"): s += 0.2
    if len(params.get("task", "")) > 20: s += 0.1
    if isinstance(result, dict) and not result.get("error"): s += 0.1
    return min(s, 1.0)
