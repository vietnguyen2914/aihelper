from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    from .common import default_intent_config_path, project_root, safe_load_json, tokenize
except ImportError:
    from common import default_intent_config_path, project_root, safe_load_json, tokenize


def _intent_config(root: Path | None = None) -> List[Dict[str, Any]]:
    root = root or project_root()
    project_config = root / "ai" / "system" / "intents.json"
    config = safe_load_json(project_config, default=None)
    if config is None:
        config = safe_load_json(default_intent_config_path(), default={})
    intents = config.get("intents", []) if isinstance(config, dict) else []
    return [item for item in intents if isinstance(item, dict) and isinstance(item.get("name"), str)]


def _learned_intent_keywords(root: Path | None = None) -> Dict[str, Dict[str, int]]:
    root = root or project_root()
    learned = safe_load_json(root / "ai" / "system" / "learned_keywords.json", default={})
    intents = learned.get("intents", {}) if isinstance(learned, dict) else {}
    return intents if isinstance(intents, dict) else {}


def detect_intent(user_prompt: str, root: Path | None = None) -> Dict[str, Any]:
    prompt_tokens = set(tokenize(user_prompt))
    intents = _intent_config(root)
    learned_keywords = _learned_intent_keywords(root)

    ranked: List[Dict[str, Any]] = []
    for intent in intents:
        name = str(intent["name"])
        keywords = set(tokenize(" ".join(str(item) for item in intent.get("keywords", []))))
        verbs = set(tokenize(" ".join(str(item) for item in intent.get("verbs", []))))

        evidence_score = 0
        matched = sorted(prompt_tokens & keywords)
        evidence_score += len(matched) * 4

        if prompt_tokens & verbs:
            evidence_score += 5

        learned = learned_keywords.get(name, {})
        if isinstance(learned, dict):
            for token in prompt_tokens:
                weight = learned.get(token)
                if isinstance(weight, int) and weight > 0:
                    evidence_score += min(weight, 5)

        score = evidence_score + (int(intent.get("priority", 0)) if evidence_score > 0 else 0)
        ranked.append(
            {
                "name": name,
                "description": intent.get("description", ""),
                "planning_style": intent.get("planning_style", "deliver"),
                "score": score,
                "matched_keywords": matched,
            }
        )

    ranked.sort(key=lambda item: (-item["score"], item["name"]))
    if not ranked or ranked[0]["score"] <= 0:
        return {
            "name": "implement",
            "description": "Default implementation intent.",
            "planning_style": "deliver",
            "score": 0,
            "matched_keywords": [],
            "confidence": 0.0,
        }

    best = dict(ranked[0])
    total = sum(max(item["score"], 0) for item in ranked if item["score"] > 0) or 1
    best["confidence"] = round(best["score"] / total, 4)
    return best

