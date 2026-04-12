from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    from .common import kebab_case, normalize_identifier, project_root, safe_load_json, safe_write_json
except ImportError:
    from common import kebab_case, normalize_identifier, project_root, safe_load_json, safe_write_json


def _normalize_keywords(values: List[Any]) -> List[str]:
    keywords: List[str] = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        keyword = normalize_identifier(value, separator="-").replace("-", " ").strip().replace(" ", "-")
        keyword = keyword.lower().strip("-")
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        keywords.append(keyword)
        if len(keywords) >= 15:
            break
    return keywords


def _validate_discovery_result(discovery_result: Dict[str, Any]) -> Dict[str, Any] | None:
    if not isinstance(discovery_result, dict):
        return None
    feature_name = discovery_result.get("feature_name")
    confidence = discovery_result.get("confidence", 0.0)
    exists_in_codebase = bool(discovery_result.get("exists_in_codebase", False))
    components = discovery_result.get("components", {})
    flows = discovery_result.get("flows", [])
    suggested = discovery_result.get("suggested_ai_feature", {})

    if not isinstance(feature_name, str) or not feature_name.strip():
        return None
    if not isinstance(confidence, (int, float)):
        return None
    if not isinstance(components, dict) or not isinstance(flows, list) or not isinstance(suggested, dict):
        return None

    canonical_feature = normalize_identifier(feature_name, separator="_")
    return {
        "feature_name": canonical_feature,
        "exists_in_codebase": exists_in_codebase,
        "confidence": max(0.0, min(float(confidence), 1.0)),
        "keywords": _normalize_keywords(discovery_result.get("keywords", [])),
        "flows": [item for item in flows if isinstance(item, dict)],
        "suggested_ai_feature": {
            "purpose": str(suggested.get("purpose", "")).strip(),
            "entry_points": [str(item) for item in suggested.get("entry_points", []) if isinstance(item, str)][:15],
            "core_entities": [str(item) for item in suggested.get("core_entities", []) if isinstance(item, str)][:15],
            "keywords": _normalize_keywords(suggested.get("keywords", [])),
            "notes": [str(item) for item in suggested.get("notes", []) if isinstance(item, str)][:15],
        },
    }


def _load_index(path: Path, key: str) -> tuple[List[Dict[str, Any]], str]:
    data = safe_load_json(path, default=[])
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)], "list"
    if isinstance(data, dict):
        values = data.get(key, [])
        if isinstance(values, list):
            return [item for item in values if isinstance(item, dict)], "dict"
    return [], "list"


def _write_index(path: Path, key: str, items: List[Dict[str, Any]], mode: str) -> None:
    if mode == "dict":
        safe_write_json(path, {key: items})
    else:
        safe_write_json(path, items)


def update_ai_kb(discovery_result: Dict[str, Any], root: Path | None = None) -> Dict[str, Any]:
    root = root or project_root()
    validated = _validate_discovery_result(discovery_result)
    if validated is None:
        return {"updated": False, "reason": "invalid_discovery_result"}
    if not (root / "ai").exists():
        return {"updated": False, "reason": "target_project_has_no_ai_directory"}
    if not validated["exists_in_codebase"]:
        return {"updated": False, "reason": "feature_not_confirmed_in_codebase"}
    if validated["confidence"] < 0.7:
        return {"updated": False, "reason": "confidence_below_threshold"}

    ai_root = root / "ai"
    features_dir = ai_root / "features"
    flows_dir = ai_root / "flows"
    feature_index_path = ai_root / "index" / "features.json"
    flow_index_path = ai_root / "index" / "flows.json"

    feature_name = validated["feature_name"]
    feature_slug = kebab_case(feature_name)
    feature_path = features_dir / f"{feature_slug}.json"
    if feature_path.exists():
        return {"updated": False, "reason": "feature_file_already_exists", "feature": feature_name}

    feature_index, feature_index_mode = _load_index(feature_index_path, "features")
    if any(isinstance(item, dict) and item.get("name") == feature_name for item in feature_index):
        return {"updated": False, "reason": "feature_already_indexed", "feature": feature_name}

    feature_payload = {
        "name": feature_name,
        "purpose": validated["suggested_ai_feature"]["purpose"],
        "entry_points": validated["suggested_ai_feature"]["entry_points"],
        "core_entities": validated["suggested_ai_feature"]["core_entities"],
        "keywords": validated["suggested_ai_feature"]["keywords"] or validated["keywords"],
        "related_ext_files": [],
        "overlaps": [],
        "notes": validated["suggested_ai_feature"]["notes"],
    }
    safe_write_json(feature_path, feature_payload)
    feature_index.append(feature_payload)
    _write_index(feature_index_path, "features", feature_index, feature_index_mode)

    flow_index, flow_index_mode = _load_index(flow_index_path, "flows")
    written_flows: List[str] = []
    for flow in validated["flows"]:
        flow_name = flow.get("name")
        if not isinstance(flow_name, str) or not flow_name.strip():
            continue
        flow_slug = kebab_case(flow_name)
        flow_path = flows_dir / f"{flow_slug}.json"
        if flow_path.exists():
            continue
        flow_payload = {
            "name": normalize_identifier(flow_name, separator="_"),
            "feature": feature_name,
            "entry_point": (
                validated["suggested_ai_feature"]["entry_points"][0]
                if validated["suggested_ai_feature"]["entry_points"]
                else "discovered flow"
            ),
            "steps": [str(item) for item in flow.get("steps", []) if isinstance(item, str)][:20],
            "db_interactions": [],
            "ext_usage": [],
        }
        safe_write_json(flow_path, flow_payload)
        flow_index.append(flow_payload)
        written_flows.append(flow_payload["name"])

    _write_index(flow_index_path, "flows", flow_index, flow_index_mode)
    return {
        "updated": True,
        "feature": feature_name,
        "feature_file": str(feature_path.relative_to(root)),
        "flow_files": written_flows,
    }

