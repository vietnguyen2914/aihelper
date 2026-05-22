from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Set

try:
    from .common import helper_root, safe_load_json, safe_write_json, tokenize
    from .ollama_fallback import call_ollama
except ImportError:
    from common import helper_root, safe_load_json, safe_write_json, tokenize
    from ollama_fallback import call_ollama


_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ỹ_]+", re.UNICODE)
_MAX_LEARNED_ENTRIES = 100
_LEARN_THRESHOLD = 3
LLM_NORMALIZE = os.environ.get("AIHELPER_LLM_NORMALIZE", "0").lower() in {"1", "true", "yes", "on"}
_TOKEN_PRIORITY = [
    "error",
    "timeout",
    "upload",
    "file",
    "image",
    "patient",
    "doctor",
    "hospital",
    "medical_record",
    "prescription",
    "appointment",
    "insurance",
    "diagnosis",
    "treatment",
    "test",
    "result",
    "storage",
    "s3",
]
_FALLBACK_TRANSLATIONS = {
    "bac si": "doctor",
    "benh an": "medical_record",
    "benh nhan": "patient",
    "benh vien": "hospital",
    "bhyt": "insurance",
    "bao hiem": "insurance",
    "chuan doan": "diagnosis",
    "cuoc hen": "appointment",
    "don thuoc": "prescription",
    "hét han": "timeout",
    "het han": "timeout",
    "hinh": "image",
    "hinh anh": "image",
    "ho so benh an": "medical_record",
    "loi": "error",
    "qua thoi gian": "timeout",
    "tai": "upload",
    "tai len": "upload",
    "tep": "file",
    "tap tin": "file",
    "thong qua": "through",
    "xet nghiem": "test",
    "ket qua": "result",
    "dieu tri": "treatment",
    "luu tru": "storage",
    "anh": "image",
    "aws": "s3",
    "bucket": "s3",
    "file": "file",
    "s3": "s3",
}


def _vi_keyword_store_path(root: Path | None = None) -> Path:
    return helper_root() / "context_engine" / "vi_keyword_store.json"


def remove_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _normalize_phrase(text: str) -> str:
    lowered = remove_accents((text or "").lower())
    lowered = re.sub(r"[^0-9a-z_]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _load_vi_store(root: Path | None = None) -> Dict[str, Dict[str, int | str]]:
    data = safe_load_json(_vi_keyword_store_path(root), default={"mapping": {}, "count": {}})
    if not isinstance(data, dict):
        return {"mapping": {}, "count": {}}
    mapping = data.get("mapping", {})
    count = data.get("count", {})
    return {
        "mapping": mapping if isinstance(mapping, dict) else {},
        "count": count if isinstance(count, dict) else {},
    }


def _save_vi_store(store: Dict[str, Dict[str, int | str]], root: Path | None = None) -> None:
    safe_write_json(_vi_keyword_store_path(root), store)


def _rule_normalize_prompt(prompt: str, root: Path | None = None) -> str:
    store = _load_vi_store(root)
    mapping = store.get("mapping", {}) if isinstance(store, dict) else {}
    tokens = [token for token in _WORD_RE.findall((prompt or "").lower()) if token and len(token) >= 2]
    normalized_tokens: List[str] = []
    seen: Set[str] = set()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.isdigit() or len(token) < 2:
            index += 1
            continue
        matched = False
        for size in (3, 2, 1):
            if index + size > len(tokens):
                continue
            phrase = " ".join(tokens[index : index + size])
            lookup_key = _normalize_phrase(phrase)
            translated = mapping.get(lookup_key) or _FALLBACK_TRANSLATIONS.get(lookup_key)
            if not translated:
                continue
            normalized = _normalize_phrase(str(translated))
            if normalized and normalized not in seen:
                seen.add(normalized)
                normalized_tokens.append(normalized)
            matched = True
            index += size
            break
        if matched:
            continue

        normalized = _normalize_phrase(token)
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_tokens.append(normalized)
        index += 1

    return " ".join(token for token in normalized_tokens if token)


def _parse_normalized_response(response: str) -> str:
    raw = (response or "").strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _normalize_phrase(raw)
    if isinstance(parsed, dict):
        value = parsed.get("normalized_prompt") or parsed.get("response") or parsed.get("text")
        if isinstance(value, str):
            return _normalize_phrase(value)
        if isinstance(value, list):
            pieces = [item for item in value if isinstance(item, str)]
            if pieces:
                return _normalize_phrase(" ".join(pieces))
    if isinstance(parsed, str):
        return _normalize_phrase(parsed)
    return _normalize_phrase(raw)


def _merge_normalized_outputs(primary: str, fallback: str) -> str:
    tokens: List[str] = []
    seen = set()
    for source in (primary, fallback):
        for token in tokenize(source):
            normalized = _normalize_phrase(token)
            if normalized and normalized not in seen:
                seen.add(normalized)
                tokens.append(normalized)

    if not tokens:
        return ""

    priority_map = {token: index for index, token in enumerate(_TOKEN_PRIORITY)}
    tokens.sort(key=lambda token: (priority_map.get(token, len(priority_map) + 1), token))
    return " ".join(tokens)


@lru_cache(maxsize=512)
def _normalize_prompt_cached(prompt: str) -> str:
    if not prompt or not prompt.strip():
        return ""

    fallback = _rule_normalize_prompt(prompt)
    if not LLM_NORMALIZE:
        merged = _merge_normalized_outputs("", fallback)
        return merged or fallback

    llm_prompt = (
        "Normalize this user prompt into short English keywords.\n"
        "Rules:\n"
        "- output JSON only\n"
        '- use the key "normalized_prompt"\n'
        "- lowercase English keywords only\n"
        "- map Vietnamese words/phrases to English equivalents\n"
        "- keep technical tokens like s3, api, json, url\n"
        "- ignore numbers and very short words\n"
        "- return at most 8 keywords separated by spaces\n\n"
        f"Input: {prompt}"
    )
    response, ok = call_ollama(llm_prompt, model_type="tiny")
    if ok and isinstance(response, str):
        normalized = _parse_normalized_response(response)
        if normalized:
            merged = _merge_normalized_outputs(normalized, fallback)
            if merged:
                return merged

    # Fallback stays deterministic when Ollama is unavailable.
    merged = _merge_normalized_outputs("", fallback)
    return merged or fallback


def normalize_prompt(prompt: str, root: Path | None = None) -> str:
    _ = root
    return _normalize_prompt_cached(prompt or "")


def _ordered_feature_keywords(feature: Dict[str, Any]) -> List[str]:
    order: List[str] = []
    seen = set()
    fields = (
        feature.get("keywords", []),
        feature.get("keywords_vi", []),
        feature.get("entry_points", []),
        feature.get("core_entities", []),
        feature.get("name", ""),
        feature.get("purpose", ""),
        feature.get("overlaps", []),
        feature.get("notes", []),
        feature.get("extensions", []),
        feature.get("related_ext_files", []),
    )
    for value in fields:
        if isinstance(value, str):
            tokens = tokenize(value.replace("_", " "))
        elif isinstance(value, list):
            tokens = []
            for item in value:
                if isinstance(item, str):
                    tokens.extend(tokenize(item.replace("_", " ")))
                elif isinstance(item, dict):
                    tokens.extend(tokenize(" ".join(str(v) for v in item.values() if isinstance(v, str))))
        elif isinstance(value, dict):
            tokens = tokenize(" ".join(str(v) for v in value.values() if isinstance(v, str)))
        else:
            tokens = []
        for token in tokens:
            normalized = _normalize_phrase(token)
            if not normalized or normalized.isdigit() or len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            order.append(normalized)
    return order


def _extract_learnable_tokens(prompt: str, normalized_prompt: str) -> List[str]:
    prompt_tokens = [token for token in _WORD_RE.findall((prompt or "").lower()) if token]
    normalized_tokens = {token for token in tokenize(normalized_prompt)}
    candidates: List[str] = []
    seen = set()
    for token in prompt_tokens:
        if len(token) < 2 or token.isdigit():
            continue
        normalized = _normalize_phrase(token)
        if not normalized or normalized in normalized_tokens:
            continue
        if normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)
    return candidates


def learn_vi_keywords(
    prompt: str,
    detected_features: List[Dict[str, Any]],
    root: Path | None = None,
) -> Dict[str, Dict[str, int | str]]:
    store = _load_vi_store(root)
    mapping = store.setdefault("mapping", {})
    count = store.setdefault("count", {})
    normalized_prompt = normalize_prompt(prompt, root=root)
    normalized_prompt_tokens = set(tokenize(normalized_prompt))

    if not isinstance(mapping, dict):
        mapping = {}
        store["mapping"] = mapping
    if not isinstance(count, dict):
        count = {}
        store["count"] = count

    primary_targets: List[str] = []
    for feature in detected_features or []:
        if not isinstance(feature, dict):
            continue
        feature_data = feature.get("feature_data", feature)
        if not isinstance(feature_data, dict):
            continue
        for keyword in _ordered_feature_keywords(feature_data):
            if keyword and keyword not in primary_targets:
                primary_targets.append(keyword)

    target_pool = [keyword for keyword in primary_targets if keyword not in normalized_prompt_tokens]
    if not target_pool:
        target_pool = primary_targets[:]

    candidates = _extract_learnable_tokens(prompt, normalized_prompt)
    assigned_targets: Set[str] = set()

    for candidate in candidates:
        if candidate in mapping:
            continue
        chosen_target = None
        for target in target_pool:
            if target not in assigned_targets:
                chosen_target = target
                break
        if chosen_target is None:
            break

        current_count = int(count.get(candidate, 0))
        next_count = current_count + 1
        count[candidate] = next_count
        if next_count >= _LEARN_THRESHOLD and len(mapping) < _MAX_LEARNED_ENTRIES:
            mapping[candidate] = chosen_target
            assigned_targets.add(chosen_target)

    _save_vi_store(store, root=root)
    return store
