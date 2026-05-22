from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

try:
    from .common import default_intent_config_path, project_root, safe_load_json, tokenize
    from .multilingual_adaptive import normalize_prompt
    from .ollama_fallback import call_ollama
except ImportError:
    from common import default_intent_config_path, project_root, safe_load_json, tokenize
    from multilingual_adaptive import normalize_prompt
    from ollama_fallback import call_ollama


LLM_INTENT = os.environ.get("AIHELPER_LLM_INTENT", "0").lower() in {"1", "true", "yes", "on"}


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


def _classify_intent_with_ollama(user_prompt: str, intents: List[Dict[str, Any]], root: Path | None = None) -> str | None:
    names = [str(intent["name"]) for intent in intents if isinstance(intent.get("name"), str)]
    if not names:
        return None

    normalized_prompt = normalize_prompt(user_prompt, root=root)
    llm_prompt = (
        "Classify the user request into exactly one allowed intent.\n"
        "Allowed intents: " + ", ".join(names) + "\n"
        "Rules:\n"
        "- output JSON only\n"
        '- use the key "intent"\n'
        "- return one of the allowed intents only\n"
        "- prefer the closest intent for the normalized prompt\n\n"
        f"Normalized prompt: {normalized_prompt}\n"
        f"Original prompt: {user_prompt}"
    )
    response, ok = call_ollama(llm_prompt, model_type="tiny")
    if not ok or not isinstance(response, str):
        return None

    raw = response.strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        candidate = raw.strip().strip('"').lower()
        return candidate if candidate in names else None

    candidate = None
    if isinstance(parsed, dict):
        value = parsed.get("intent") or parsed.get("name") or parsed.get("label")
        if isinstance(value, str):
            candidate = value.strip().lower()
    elif isinstance(parsed, str):
        candidate = parsed.strip().lower()

    return candidate if candidate in names else None


def detect_intent(user_prompt: str, root: Path | None = None) -> Dict[str, Any]:
    intents = _intent_config(root)
    normalized_prompt = normalize_prompt(user_prompt, root=root)
    prompt_tokens = set(tokenize(normalized_prompt))
    learned_keywords = _learned_intent_keywords(root)
    model_hint = _classify_intent_with_ollama(user_prompt, intents, root=root) if LLM_INTENT else None

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

        if model_hint == name:
            evidence_score += 6

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
    if model_hint:
        for item in ranked:
            if item["name"] == model_hint:
                if item["score"] <= 0:
                    item = dict(item)
                    item["score"] = 1
                    item["confidence"] = 1.0
                    return item
                best = dict(item)
                total = sum(max(entry["score"], 0) for entry in ranked if entry["score"] > 0) or 1
                best["confidence"] = round(best["score"] / total, 4)
                return best

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
