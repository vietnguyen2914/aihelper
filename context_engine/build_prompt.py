from __future__ import annotations

import json
from typing import Any, Dict, List


def rewrite_prompt(
    user_prompt: str,
    intent: Dict[str, Any],
    features: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> str:
    feature_names = [item["feature"] for item in features]
    services = sorted({item["service"] for item in features})
    feature_label = ", ".join(feature_names) if feature_names else "the closest business feature"
    service_label = ", ".join(services) if services else "the owning service"
    intent_name = intent.get("name", "implement")
    ext_note = (
        "Respect ext overrides before changing base behavior."
        if context.get("ext_overrides")
        else "No ext overrides were detected for the selected scope."
    )

    return (
        f"Intent: {intent_name}.\n"
        f"Rewrite the request as a business-feature task in {service_label}.\n"
        f"Primary feature scope: {feature_label}.\n"
        f"Original request: {user_prompt}.\n"
        "Constraints:\n"
        "- Prioritize business features over technical modules.\n"
        "- Keep context deterministic, JSON-backed, and lightweight.\n"
        f"- {ext_note}\n"
        "- Preserve related integrations and overlapping flows.\n"
        f"Selected context: {json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )


def build_prompt(user_prompt: str, context: Dict[str, Any] | str, max_total_chars: int = 0) -> str:
    if not isinstance(context, str):
        context = json.dumps(context, indent=2, ensure_ascii=False)
    target_root = ""
    if isinstance(context, str) and '"target_root"' in context:
        target_root = "You are working on the current target repository selected by the launcher.\n\n"
    result = (
        f"{target_root}"
        "Context:\n"
        f"{context}\n\n"
        "Rules:\n"
        "- Prioritize business features over modules.\n"
        "- Respect ext overrides and custom overrides before generated/base behavior.\n"
        "- Follow existing flows and keep integrations stable.\n"
        "- Prefer minimal, deterministic changes with validation steps.\n\n"
        f"Task: {user_prompt}\n"
    )

    if max_total_chars > 0 and len(result) > max_total_chars:
        # Rebuild with truncated context
        wrapper_prefix = f"{target_root}Context:\n"
        wrapper_suffix = "\n\nRules:\n- Prioritize business features over modules.\n- Respect ext overrides and custom overrides before generated/base behavior.\n- Follow existing flows and keep integrations stable.\n- Prefer minimal, deterministic changes with validation steps.\n\n"
        wrapper_suffix += f"Task: {user_prompt}\n"

        available = max_total_chars - len(wrapper_prefix) - len(wrapper_suffix)
        if available > 100:
            truncated_context = context[:available] + "\n... [context truncated to fit token budget]"
            result = f"{wrapper_prefix}{truncated_context}{wrapper_suffix}"

    return result

