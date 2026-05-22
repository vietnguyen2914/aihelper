from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from .cache import cache_paths
    from .common import safe_load_json, safe_write_json
except ImportError:
    from cache import cache_paths
    from common import safe_load_json, safe_write_json


def _memory_path(project_root: Path) -> Path:
    return cache_paths(project_root.resolve())["root"] / "working_memory.json"


def remember(project_root: Path, topic: str, note: str, tags: List[str] | None = None) -> Dict[str, Any]:
    path = _memory_path(project_root)
    data = safe_load_json(path, default={"items": []}) or {"items": []}
    item = {
        "topic": topic,
        "note": note,
        "tags": tags or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    items = [item, *data.get("items", [])][:100]
    payload = {"items": items}
    safe_write_json(path, payload)
    return {"project_root": str(project_root.resolve()), "item": item, "count": len(items)}


def recall(project_root: Path, query: str = "", limit: int = 10) -> Dict[str, Any]:
    data = safe_load_json(_memory_path(project_root), default={"items": []}) or {"items": []}
    tokens = {token.lower() for token in query.split() if token}
    items = data.get("items", [])
    if tokens:
        items = [
            item for item in items
            if tokens & set(str(item.get("topic", "") + " " + item.get("note", "") + " " + " ".join(item.get("tags", []))).lower().split())
        ]
    return {"project_root": str(project_root.resolve()), "items": items[:limit], "count": len(items[:limit])}
