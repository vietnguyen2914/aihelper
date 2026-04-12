from __future__ import annotations

from typing import Any, Dict, List

try:
    from .common import tokenize
except ImportError:
    from common import tokenize


def _flow_score(flow: Dict[str, Any], user_prompt: str) -> int:
    text = " ".join(
        [
            str(flow.get("name", "")),
            str(flow.get("entry_point", "")),
            " ".join(str(item) for item in flow.get("steps", []) if isinstance(item, str)),
        ]
    )
    flow_tokens = set(tokenize(text))
    prompt_tokens = set(tokenize(user_prompt))
    score = len(prompt_tokens & flow_tokens) * 2

    if {"timeout", "session", "auth", "sign", "signin", "signing"} & prompt_tokens:
        score += len(flow_tokens & {"login", "session", "bootstrap", "token", "jwt", "auth"}) * 3
    if {"register", "signup"} & prompt_tokens:
        score += len(flow_tokens & {"register", "registration"}) * 3
    return score


def _primary_flow(context: Dict[str, Any], user_prompt: str) -> Dict[str, Any] | None:
    best_flow: Dict[str, Any] | None = None
    best_score = -1
    for service in context.get("services", []):
        for flow in service.get("flows", []):
            if not isinstance(flow, dict):
                continue
            score = _flow_score(flow, user_prompt)
            if score > best_score:
                best_score = score
                best_flow = flow
    return best_flow


def build_execution_plan(
    user_prompt: str,
    intent: Dict[str, Any],
    features: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, str]]:
    feature_names = [item["feature"] for item in features]
    services = sorted({item["service"] for item in features})
    ext_overrides = context.get("ext_overrides", [])
    primary_flow = _primary_flow(context, user_prompt)
    flow_name = primary_flow.get("name") if isinstance(primary_flow, dict) else "relevant flow"
    flow_entry = primary_flow.get("entry_point") if isinstance(primary_flow, dict) else "business entry point"
    feature_label = ", ".join(feature_names) if feature_names else "matched business feature"
    service_label = ", ".join(services) if services else "owning service"

    plan = [
        {
            "step": "scope",
            "details": f"Confirm that the request belongs to {feature_label} in {service_label} and avoid drifting into technical module boundaries.",
        },
        {
            "step": "trace",
            "details": f"Trace {flow_name} from {flow_entry} and identify the exact backend or frontend handoff that affects '{user_prompt}'.",
        },
    ]

    if ext_overrides:
        plan.append(
            {
                "step": "check-overrides",
                "details": "Inspect detected ext overrides before changing base implementation so custom behavior remains authoritative.",
            }
        )

    style = intent.get("planning_style")
    if style == "repair":
        plan.extend(
            [
                {
                    "step": "repair",
                    "details": "Apply the smallest deterministic fix at the owning business boundary, then review overlapping features and integrations for regressions.",
                },
                {
                    "step": "validate",
                    "details": "Validate the affected flow, adjacent integrations, and timeout or session edge cases after the fix.",
                },
            ]
        )
    elif style == "investigate":
        plan.extend(
            [
                {
                    "step": "inspect",
                    "details": "Collect the current behavior, configuration, and persisted state transitions before proposing any code change.",
                },
                {
                    "step": "summarize",
                    "details": "Summarize the likely root cause, impacted features, and the lowest-risk change surface.",
                },
            ]
        )
    elif style == "validate":
        plan.extend(
            [
                {
                    "step": "cover",
                    "details": "Design focused validation around the main flow, the most likely failure edges, and feature overlap boundaries.",
                },
                {
                    "step": "report",
                    "details": "Report what passed, what failed, and any remaining risk that still lacks deterministic coverage.",
                },
            ]
        )
    else:
        plan.extend(
            [
                {
                    "step": "implement",
                    "details": "Implement the requested behavior inside the owning feature while keeping existing routes, APIs, and persisted data contracts stable.",
                },
                {
                    "step": "validate",
                    "details": "Validate the primary flow and dependent integrations after the change.",
                },
            ]
        )

    return plan

