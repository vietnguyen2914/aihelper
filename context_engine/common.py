from __future__ import annotations

import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List


_JSON_CACHE: Dict[str, tuple[float, Any]] = {}

STOP_WORDS = {
    "a",
    "an",
    "and",
    "api",
    "app",
    "application",
    "be",
    "build",
    "by",
    "do",
    "for",
    "from",
    "get",
    "in",
    "into",
    "is",
    "it",
    "main",
    "module",
    "of",
    "on",
    "or",
    "service",
    "system",
    "that",
    "the",
    "this",
    "to",
    "ui",
    "use",
    "with",
}


def helper_root() -> Path:
    return Path(__file__).resolve().parents[1]


def project_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_root = os.environ.get("AIHELPER_TARGET_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path.cwd().resolve()


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def normalize_identifier(text: str, separator: str = "_") -> str:
    normalized = re.sub(r"[^a-z0-9]+", separator, (text or "").lower()).strip(separator)
    normalized = re.sub(rf"{re.escape(separator)}+", separator, normalized)
    return normalized or "unknown_feature"


def kebab_case(text: str) -> str:
    return normalize_identifier(text, separator="-")


def tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    seen = set()
    for raw_token in normalize(text).split():
        if len(raw_token) < 2 or raw_token in STOP_WORDS:
            continue
        variants = {raw_token}
        if raw_token.endswith("ing") and len(raw_token) > 5:
            variants.add(raw_token[:-3])
        if raw_token.endswith("ed") and len(raw_token) > 4:
            variants.add(raw_token[:-2])
        if raw_token.endswith("s") and len(raw_token) > 4:
            variants.add(raw_token[:-1])
        if raw_token == "signin":
            variants.update({"sign", "login"})
        if raw_token == "signup":
            variants.update({"sign", "register"})
        for token in variants:
            if len(token) < 2 or token in STOP_WORDS or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


def safe_load_json(path: Path, default: Any = None) -> Any:
    try:
        stat = path.stat()
    except OSError:
        return default

    cached = _JSON_CACHE.get(str(path))
    if cached and cached[0] == stat.st_mtime:
        return cached[1]

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default

    _JSON_CACHE[str(path)] = (stat.st_mtime, data)
    return data


def safe_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as temp:
        json.dump(data, temp, indent=2, ensure_ascii=False)
        temp.write("\n")
        tmp_path = Path(temp.name)
    tmp_path.replace(path)
    try:
        stat = path.stat()
    except OSError:
        _JSON_CACHE.pop(str(path), None)
        return
    _JSON_CACHE[str(path)] = (stat.st_mtime, data)


def _as_list(data: Any, key: str) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        values = data.get(key, [])
        if isinstance(values, list):
            return [item for item in values if isinstance(item, dict)]
    return []


def discover_services(root: Path | None = None) -> List[Dict[str, Path | str]]:
    root = root or project_root()
    candidates = [root]
    try:
        for child in root.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                candidates.append(child)
    except OSError:
        return []

    services: List[Dict[str, Path | str]] = []
    seen = set()
    for candidate in candidates:
        ai_dir = candidate / "ai"
        feature_index = ai_dir / "index" / "features.json"
        if not feature_index.exists():
            continue
        resolved = str(candidate.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        services.append({"name": candidate.name, "root": candidate, "ai_dir": ai_dir})
    return services


def load_feature_index(service: Dict[str, Path | str]) -> List[Dict[str, Any]]:
    return _as_list(safe_load_json(Path(service["ai_dir"]) / "index" / "features.json", default=[]), "features")


def load_flow_index(service: Dict[str, Path | str]) -> List[Dict[str, Any]]:
    return _as_list(safe_load_json(Path(service["ai_dir"]) / "index" / "flows.json", default=[]), "flows")


def load_integration_index(service: Dict[str, Path | str]) -> List[Dict[str, Any]]:
    return _as_list(
        safe_load_json(Path(service["ai_dir"]) / "index" / "integrations.json", default=[]),
        "integrations",
    )


def collect_text_tokens(values: Iterable[Any]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if isinstance(value, str):
            tokens.update(tokenize(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    tokens.update(tokenize(item))
                elif isinstance(item, dict):
                    for dict_value in item.values():
                        if isinstance(dict_value, str):
                            tokens.update(tokenize(dict_value))
        elif isinstance(value, dict):
            for dict_value in value.values():
                if isinstance(dict_value, str):
                    tokens.update(tokenize(dict_value))
    return tokens


def ai_json_file_candidates(directory: Path, logical_name: str) -> List[Path]:
    normalized = normalize_identifier(logical_name, separator="_")
    kebab = kebab_case(logical_name)
    candidates = [
        directory / f"{logical_name}.json",
        directory / f"{normalized}.json",
        directory / f"{kebab}.json",
    ]

    unique: List[Path] = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def default_intent_config_path() -> Path:
    return helper_root() / "ai" / "system" / "intents.json"


def default_shared_keyword_path() -> Path:
    return helper_root() / "ai" / "system" / "shared_keywords.json"

