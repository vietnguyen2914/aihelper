from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set

try:
    from .common import collect_text_tokens, discover_services, load_feature_index, project_root, tokenize
    from .learning import _load_learned
except ImportError:
    from common import collect_text_tokens, discover_services, load_feature_index, project_root, tokenize
    from learning import _load_learned


def _learned_feature_keywords(root: Path | None = None) -> Dict[str, Dict[str, int]]:
    learned = _load_learned(root)
    features = learned.get("features", {}) if isinstance(learned, dict) else {}
    return features if isinstance(features, dict) else {}


def feature_keywords(feature: Dict[str, Any], root: Path | None = None) -> Set[str]:
    name = str(feature.get("name", ""))
    keywords = collect_text_tokens(
        [
            feature.get("name", ""),
            feature.get("purpose", ""),
            feature.get("entry_points", []),
            feature.get("core_entities", []),
            feature.get("overlaps", []),
            feature.get("notes", []),
            feature.get("extensions", []),
            feature.get("related_ext_files", []),
        ]
    )
    if name:
        keywords.update(tokenize(name.replace("_", " ")))

    learned = _learned_feature_keywords(root).get(name, {})
    if isinstance(learned, dict):
        for token, weight in learned.items():
            if isinstance(token, str) and isinstance(weight, int) and weight > 0:
                keywords.add(token)
    return {token for token in keywords if len(token) > 2}


def score_feature(user_prompt: str, feature: Dict[str, Any], root: Path | None = None) -> Dict[str, Any]:
    prompt_tokens = set(tokenize(user_prompt))
    keywords = feature_keywords(feature, root=root)
    matched_keywords = sorted(prompt_tokens & keywords)
    score = len(matched_keywords) * 4

    for entry in feature.get("entry_points", []):
        if isinstance(entry, str):
            score += len(prompt_tokens & set(tokenize(entry))) * 2

    for entity in feature.get("core_entities", []):
        if isinstance(entity, str):
            score += len(prompt_tokens & set(tokenize(entity))) * 2

    name = feature.get("name", "")
    if isinstance(name, str):
        normalized_name = name.replace("_", " ").lower()
        if normalized_name and normalized_name in user_prompt.lower():
            score += 6

    return {"feature": name, "score": score, "matched_keywords": matched_keywords}


def detect_feature_matches(user_prompt: str, root: Path | None = None, top_n: int = 3) -> List[Dict[str, Any]]:
    root = root or project_root()
    ranked: List[Dict[str, Any]] = []

    for service in discover_services(root):
        for feature in load_feature_index(service):
            match = score_feature(user_prompt, feature, root=root)
            if match["score"] <= 0 or not isinstance(match["feature"], str):
                continue
            ranked.append(
                {
                    "service": str(service["name"]),
                    "service_root": str(Path(service["root"]).resolve()),
                    "feature": str(match["feature"]),
                    "feature_data": feature,
                    "score": match["score"],
                    "matched_keywords": match["matched_keywords"],
                }
            )

    ranked.sort(key=lambda item: (-item["score"], item["service"], item["feature"]))
    if not ranked:
        return []

    best_score = ranked[0]["score"]
    threshold = max(2, best_score - 3)
    filtered = [item for item in ranked if item["score"] >= threshold]
    return filtered[:top_n]


def detect_features(user_prompt: str, root: Path | None = None) -> List[str]:
    return [item["feature"] for item in detect_feature_matches(user_prompt, root=root)]

