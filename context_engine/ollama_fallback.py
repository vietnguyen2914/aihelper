"""Local Ollama fallback for unknown prompts.

This module keeps the context engine open-world:
- if a feature matches, normal execution continues
- if no feature matches, try Ollama/Qwen locally
- if Ollama or the model is unavailable, print the prompt only so it can be pasted into GPT or Claude
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from .discovery import discover_feature_from_codebase
except ImportError:
    from discovery import discover_feature_from_codebase


DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:latest")


def build_discovery_prompt(user_prompt: str, root: Path | None = None) -> str:
    """Build the prompt sent to Ollama or a general LLM for unknown-feature discovery."""
    discovery = discover_feature_from_codebase(user_prompt, root=root)
    schema = {
        "feature_name": "string",
        "exists_in_codebase": True,
        "confidence": 0.0,
        "keywords": ["string"],
        "components": {
            "services": ["string"],
            "controllers": ["string"],
            "entities": ["string"],
            "integrations": ["string"],
        },
        "flows": [
            {
                "name": "string",
                "steps": ["string"],
            }
        ],
        "suggested_ai_feature": {
            "purpose": "string",
            "entry_points": ["string"],
            "core_entities": ["string"],
            "keywords": ["string"],
            "notes": ["string"],
        },
    }
    return (
        "You are a senior software architect analyzing an existing codebase.\n"
        "The current AI knowledge base did NOT detect a matching feature, but the behavior may already exist.\n"
        "Analyze only the evidence provided below. Do not invent systems, services, or entities that are not justified.\n"
        "Return STRICT JSON only. No markdown. No prose. No code fences.\n"
        "If evidence is weak, set exists_in_codebase to false and lower confidence.\n"
        "Keep keywords lowercase, deduplicated, and at most 15 items.\n\n"
        f"User request: {user_prompt}\n\n"
        f"Codebase snapshot: {json.dumps(discovery, ensure_ascii=False)}\n\n"
        f"Required JSON schema: {json.dumps(schema, ensure_ascii=False)}"
    )


def build_manual_fallback_prompt(user_prompt: str, root: Path | None = None) -> str:
    """Build a short prompt for GPT or Claude when Ollama is unavailable."""
    discovery = discover_feature_from_codebase(user_prompt, root=root)
    return (
        "You are a senior software architect.\n"
        "Discover the likely feature from this codebase and return STRICT JSON only.\n"
        f"User request: {user_prompt}\n"
        f"Codebase snapshot: {json.dumps(discovery, ensure_ascii=False)}\n"
        "Return: feature_name, exists_in_codebase, confidence, keywords, components, flows, suggested_ai_feature."
    )


def _request_json(method: str, url: str, payload: Optional[dict] = None, timeout: int = 20) -> dict:
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def _available_models(base_url: str = DEFAULT_OLLAMA_URL) -> list[str]:
    try:
        data = _request_json("GET", f"{base_url}/api/tags")
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return []

    models = data.get("models", [])
    if not isinstance(models, list):
        return []

    names: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _normalize_model_name(model: str) -> str:
    return model.strip().lower()


def _resolve_model(model: str = DEFAULT_MODEL, base_url: str = DEFAULT_OLLAMA_URL) -> str | None:
    """Resolve the best local Ollama model name, preferring the requested model."""
    requested = _normalize_model_name(model)
    names = _available_models(base_url=base_url)
    if not names:
        return None

    normalized = {name.lower(): name for name in names}

    if requested in normalized:
        return normalized[requested]

    # Accept prefix matches like "qwen2.5" -> "qwen2.5:latest"
    for name in names:
        lowered = name.lower()
        if lowered.startswith(requested + ":") or lowered == requested:
            return name

    # Prefer any qwen2.5 family model if the exact request is unavailable.
    if requested.startswith("qwen2.5") or "qwen2.5" in requested:
        for name in names:
            if name.lower().startswith("qwen2.5"):
                return name

    return names[0]


def model_available(model: str = DEFAULT_MODEL, base_url: str = DEFAULT_OLLAMA_URL) -> bool:
    return _resolve_model(model=model, base_url=base_url) is not None


def generate_with_ollama(prompt: str, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_OLLAMA_URL) -> Tuple[Optional[str], bool]:
    """Generate text with Ollama when the model is available."""
    resolved_model = _resolve_model(model=model, base_url=base_url)
    if not resolved_model:
        return None, False

    try:
        data = _request_json(
            "POST",
            f"{base_url}/api/generate",
            payload={
                "model": resolved_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
        )
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None, False

    response = data.get("response")
    if isinstance(response, str) and response.strip():
        return response, True
    return None, False
