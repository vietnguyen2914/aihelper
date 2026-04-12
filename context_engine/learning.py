from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    from .common import helper_root, project_root, safe_load_json, safe_write_json, tokenize
except ImportError:
    from common import helper_root, project_root, safe_load_json, safe_write_json, tokenize


def _project_system_dir(root: Path | None = None) -> Path:
    root = root or project_root()
    return root / "ai" / "system"


def _shared_system_dir() -> Path:
    return helper_root() / "ai" / "system"


def _learned_keywords_path(root: Path | None = None) -> Path:
    project_path = _project_system_dir(root) / "learned_keywords.json"
    if project_path.parent.parent.exists():
        return project_path
    return _shared_system_dir() / "learned_keywords.json"


def _feedback_log_path(root: Path | None = None) -> Path:
    project_path = _project_system_dir(root) / "feedback_log.json"
    if project_path.parent.parent.exists():
        return project_path
    return _shared_system_dir() / "feedback_log.json"


def _load_learned(root: Path | None = None) -> Dict[str, Any]:
    data = safe_load_json(_learned_keywords_path(root), default={})
    if not isinstance(data, dict):
        return {"features": {}, "intents": {}, "ignored_tokens": {}}
    data.setdefault("features", {})
    data.setdefault("intents", {})
    data.setdefault("ignored_tokens", {})
    return data


def feedback_summary(root: Path | None = None) -> Dict[str, Any]:
    data = safe_load_json(_feedback_log_path(root), default={"entries": []})
    entries = data.get("entries", []) if isinstance(data, dict) else []
    accepted = 0
    rejected = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("accepted"):
            accepted += 1
        else:
            rejected += 1
    total = accepted + rejected
    return {
        "entries": total,
        "accepted": accepted,
        "rejected": rejected,
        "acceptance_rate": round(accepted / total, 4) if total else 0.0,
    }


def record_feedback(
    user_prompt: str,
    detected_intent: str,
    detected_features: List[str],
    accepted: bool,
    rating: int = 0,
    notes: str = "",
    root: Path | None = None,
) -> Dict[str, Any]:
    learned = _load_learned(root)
    tokens = [token for token in tokenize(user_prompt) if len(token) > 2]
    delta = 1 if accepted or rating >= 4 else -1

    intent_bucket = learned["intents"].setdefault(detected_intent, {})
    for token in tokens:
        current = int(intent_bucket.get(token, 0))
        next_value = max(0, current + delta)
        if next_value == 0:
            intent_bucket.pop(token, None)
        else:
            intent_bucket[token] = next_value

    for feature_name in detected_features:
        feature_bucket = learned["features"].setdefault(feature_name, {})
        for token in tokens:
            current = int(feature_bucket.get(token, 0))
            next_value = max(0, current + delta)
            if next_value == 0:
                feature_bucket.pop(token, None)
            else:
                feature_bucket[token] = next_value

    if not accepted:
        ignored = learned["ignored_tokens"]
        for token in tokens:
            ignored[token] = int(ignored.get(token, 0)) + 1

    safe_write_json(_learned_keywords_path(root), learned)

    feedback_log = safe_load_json(_feedback_log_path(root), default={"entries": []})
    if not isinstance(feedback_log, dict):
        feedback_log = {"entries": []}
    entries = feedback_log.setdefault("entries", [])
    entries.append(
        {
            "prompt": user_prompt,
            "intent": detected_intent,
            "features": detected_features,
            "accepted": accepted,
            "rating": rating,
            "notes": notes,
        }
    )
    feedback_log["entries"] = entries[-200:]
    safe_write_json(_feedback_log_path(root), feedback_log)
    return feedback_summary(root)

