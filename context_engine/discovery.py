from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    from .common import normalize_identifier, project_root, tokenize
except ImportError:
    from common import normalize_identifier, project_root, tokenize


def _sample_paths(root: Path, patterns: List[str], limit: int) -> List[str]:
    results: List[str] = []
    seen = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            relative = str(path.relative_to(root))
            if relative in seen:
                continue
            seen.add(relative)
            results.append(relative)
            if len(results) >= limit:
                return results
    return results


def discover_feature_from_codebase(user_prompt: str, root: Path | None = None) -> Dict[str, Any]:
    root = root or project_root()
    prompt_tokens = tokenize(user_prompt)
    confidence = 0.2 if prompt_tokens else 0.0
    feature_name = normalize_identifier(" ".join(prompt_tokens[:4]) or "unknown_feature")

    backend_root = root / "src"
    if not backend_root.exists():
        backend_root = root / "backend"
    frontend_root = root / "frontend"

    controllers = _sample_paths(root, ["**/*Controller.java", "**/*Resource.java", "**/*Controller.kt"], 12)
    services = _sample_paths(root, ["**/*Service.java", "**/*Service.kt", "**/*service*.js"], 12)
    entities = _sample_paths(root, ["**/*Entity.java", "**/domain/*.java", "**/models/*.js"], 12)
    pages = _sample_paths(root, ["**/pages/**/*.jsx", "**/pages/**/*.tsx", "**/app/**/*.tsx"], 10)

    if controllers or services or entities or pages:
        confidence = 0.45

    return {
        "feature_name": feature_name,
        "exists_in_codebase": bool(controllers or services or entities or pages),
        "confidence": confidence,
        "keywords": prompt_tokens[:15],
        "components": {
            "services": services,
            "controllers": controllers,
            "entities": entities,
            "integrations": [],
        },
        "flows": [],
        "suggested_ai_feature": {
            "purpose": f"Discovered candidate feature for request: {user_prompt}",
            "entry_points": controllers[:4] + pages[:4],
            "core_entities": entities[:6],
            "keywords": prompt_tokens[:15],
            "notes": [
                f"Derived from filesystem inspection under {root}",
                "No indexed ai feature matched the request strongly enough.",
            ],
        },
    }

