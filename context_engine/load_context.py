from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

try:
    from .common import (
        ai_json_file_candidates,
        discover_services,
        load_feature_index,
        load_flow_index,
        load_integration_index,
        project_root,
        safe_load_json,
        tokenize,
    )
except ImportError:
    from common import (
        ai_json_file_candidates,
        discover_services,
        load_feature_index,
        load_flow_index,
        load_integration_index,
        project_root,
        safe_load_json,
        tokenize,
    )


def _load_feature_payload(service: Dict[str, Path | str], feature_name: str) -> Dict[str, Any] | None:
    feature_dir = Path(service["ai_dir"]) / "features"
    for candidate in ai_json_file_candidates(feature_dir, feature_name):
        data = safe_load_json(candidate, default=None)
        if isinstance(data, dict):
            return data
    for feature in load_feature_index(service):
        if feature.get("name") == feature_name:
            return feature
    return None


def _detect_ext_overrides(service_root: Path, feature_names: List[str], feature_payloads: List[Dict[str, Any]]) -> List[str]:
    matches: List[str] = []
    seen = set()
    for payload in feature_payloads:
        for key in ("related_ext_files", "extensions", "ext_usage"):
            values = payload.get(key, [])
            if not isinstance(values, list):
                continue
            for item in values:
                path = item.get("path") if isinstance(item, dict) else item
                if not isinstance(path, str):
                    continue
                if path in seen:
                    continue
                seen.add(path)
                matches.append(path)
    if len(matches) >= 8:
        return matches[:12]

    feature_tokens = set()
    for feature_name in feature_names:
        feature_tokens.update(tokenize(feature_name.replace("_", " ")))

    if not feature_tokens:
        return matches[:12]

    try:
        for path in service_root.rglob("*"):
            if not path.is_file():
                continue
            relative = str(path.relative_to(service_root))
            if "/ext/" not in f"/{relative.replace(chr(92), '/')}/" and "Ext" not in path.name:
                continue
            path_tokens = set(tokenize(relative))
            if feature_tokens & path_tokens and relative not in seen:
                seen.add(relative)
                matches.append(relative)
            if len(matches) >= 12:
                break
    except OSError:
        pass

    return matches[:12]


def _service_context(service: Dict[str, Path | str], feature_names: List[str]) -> Dict[str, Any]:
    service_root = Path(service["root"])
    flows = load_flow_index(service)
    integrations = load_integration_index(service)
    feature_payloads = [
        payload
        for feature_name in feature_names
        for payload in [_load_feature_payload(service, feature_name)]
        if payload
    ]
    selected_flows = [flow for flow in flows if flow.get("feature") in feature_names][:8]
    selected_integrations = [
        item
        for item in integrations
        if item.get("source_feature") in feature_names or item.get("target_feature") in feature_names
    ][:10]
    ext_overrides = _detect_ext_overrides(service_root, feature_names, feature_payloads)

    return {
        "service": service["name"],
        "root": str(service_root.resolve()),
        "selected_features": feature_names,
        "features": feature_payloads,
        "flows": selected_flows,
        "integrations": selected_integrations,
        "ext_overrides": ext_overrides,
    }


def load_context_bundle(
    ranked_features: List[Dict[str, Any]],
    max_chars: int = 12000,
    root: Path | None = None,
) -> Dict[str, Any]:
    root = root or project_root()
    service_lookup = {str(service["name"]): service for service in discover_services(root)}
    feature_map: Dict[str, List[str]] = {}
    for match in ranked_features:
        service_name = str(match["service"])
        feature_name = str(match["feature"])
        feature_map.setdefault(service_name, [])
        if feature_name not in feature_map[service_name]:
            feature_map[service_name].append(feature_name)

    services = []
    ext_overrides: List[Dict[str, Any]] = []
    for service_name, feature_names in feature_map.items():
        service = service_lookup.get(service_name)
        if not service:
            continue
        payload = _service_context(service, feature_names)
        services.append(payload)
        if payload["ext_overrides"]:
            ext_overrides.append({"service": service_name, "paths": payload["ext_overrides"]})

    context = {
        "target_root": str(root.resolve()),
        "services": services,
        "ext_overrides": ext_overrides,
        "context_limit_chars": max_chars,
        "truncated": False,
    }

    rendered = json.dumps(context, indent=2, ensure_ascii=False)
    if len(rendered) <= max_chars:
        return context

    reduced_services = []
    for service in services:
        reduced_services.append(
            {
                "service": service["service"],
                "root": service["root"],
                "selected_features": service["selected_features"],
                "features": service["features"][:2],
                "flows": service["flows"][:3],
                "integrations": service["integrations"][:4],
                "ext_overrides": service["ext_overrides"][:5],
            }
        )

    return {
        "target_root": str(root.resolve()),
        "services": reduced_services,
        "ext_overrides": ext_overrides,
        "context_limit_chars": max_chars,
        "truncated": True,
        "truncation_note": "Context was truncated to stay within size limits.",
    }


def load_context(feature_names: List[str], max_chars: int = 12000, root: Path | None = None) -> str:
    root = root or project_root()
    ranked = [{"service": root.name, "feature": name} for name in feature_names]
    return json.dumps(load_context_bundle(ranked, max_chars=max_chars, root=root), indent=2, ensure_ascii=False)
