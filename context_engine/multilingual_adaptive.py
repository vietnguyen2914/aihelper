from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

try:
    from .common import collect_text_tokens, helper_root, safe_load_json, safe_write_json, tokenize
except ImportError:
    from common import collect_text_tokens, helper_root, safe_load_json, safe_write_json, tokenize


_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ỹ_]+", re.UNICODE)
_MAX_LEARNED_ENTRIES = 100
_LEARN_THRESHOLD = 3
_VI_STOPWORDS = {
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


def _base_synonyms_path() -> Path:
    return helper_root() / "context_engine" / "synonyms.json"


def _medical_dictionary_path() -> Path:
    return helper_root() / "context_engine" / "medical_dictionary.json"


def _vi_keyword_store_path(root: Path | None = None) -> Path:
    return helper_root() / "context_engine" / "vi_keyword_store.json"


def remove_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _normalize_phrase(text: str) -> str:
    lowered = remove_accents((text or "").lower())
    lowered = re.sub(r"[^0-9a-z_]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _load_dict(path: Path, default: Any) -> Any:
    data = safe_load_json(path, default=default)
    return data if isinstance(data, type(default)) else default


def _load_base_synonyms() -> Dict[str, List[str]]:
    data = safe_load_json(_base_synonyms_path(), default={})
    if not isinstance(data, dict):
        return {}
    result: Dict[str, List[str]] = {}
    for canonical, values in data.items():
        if not isinstance(canonical, str):
            continue
        phrases: List[str] = [canonical]
        if isinstance(values, list):
            phrases.extend(value for value in values if isinstance(value, str))
        cleaned: List[str] = []
        seen = set()
        for phrase in phrases:
            normalized = _normalize_phrase(phrase)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        if cleaned:
            result[_normalize_phrase(canonical)] = cleaned
    return result


def _load_medical_dictionary() -> Dict[str, List[str]]:
    data = safe_load_json(_medical_dictionary_path(), default={})
    if not isinstance(data, dict):
        return {}
    result: Dict[str, List[str]] = {}
    for canonical, values in data.items():
        if not isinstance(canonical, str):
            continue
        phrases: List[str] = [canonical]
        if isinstance(values, list):
            phrases.extend(value for value in values if isinstance(value, str))
        cleaned: List[str] = []
        seen = set()
        for phrase in phrases:
            normalized = _normalize_phrase(phrase)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        if cleaned:
            result[_normalize_phrase(canonical)] = cleaned
    return result


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


def merge_dictionaries(root: Path | None = None) -> Dict[str, List[str]]:
    combined: Dict[str, List[str]] = {}

    for dictionary in (_load_base_synonyms(), _load_medical_dictionary()):
        for canonical, values in dictionary.items():
            bucket = combined.setdefault(_normalize_phrase(canonical), [])
            seen = set(bucket)
            for value in values:
                normalized = _normalize_phrase(value)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    bucket.append(normalized)

    vi_store = _load_vi_store(root)
    mapping = vi_store.get("mapping", {})
    if isinstance(mapping, dict):
        for vietnamese, canonical in mapping.items():
            if not isinstance(vietnamese, str) or not isinstance(canonical, str):
                continue
            bucket = combined.setdefault(_normalize_phrase(canonical), [])
            normalized_vietnamese = _normalize_phrase(vietnamese)
            if normalized_vietnamese and normalized_vietnamese not in bucket:
                bucket.append(normalized_vietnamese)

    return combined


def _lookup_table(root: Path | None = None) -> Tuple[Dict[str, str], int]:
    lookup: Dict[str, str] = {}
    max_words = 1
    for canonical, aliases in merge_dictionaries(root=root).items():
        for alias in aliases + [canonical]:
            normalized = _normalize_phrase(alias)
            if not normalized:
                continue
            lookup.setdefault(normalized, canonical)
            max_words = max(max_words, len(normalized.split()))
    return lookup, max_words


def _english_terms(root: Path | None = None) -> Set[str]:
    terms: Set[str] = set()
    for canonical, aliases in merge_dictionaries(root=root).items():
        terms.add(_normalize_phrase(canonical))
        terms.update(_normalize_phrase(alias) for alias in aliases)

    try:
        from .common import discover_services, load_feature_index
    except ImportError:
        from common import discover_services, load_feature_index

    for service in discover_services(root):
        for feature in load_feature_index(service):
            terms.update(tokenize(" ".join(str(item) for item in feature.get("entry_points", []) if isinstance(item, str))))
            terms.update(tokenize(" ".join(str(item) for item in feature.get("core_entities", []) if isinstance(item, str))))
            terms.update(tokenize(" ".join(str(item) for item in feature.get("keywords", []) if isinstance(item, str))))
            name = feature.get("name")
            if isinstance(name, str):
                terms.update(tokenize(name.replace("_", " ")))
    return {term for term in terms if term}


def is_vietnamese_word(word: str, root: Path | None = None) -> bool:
    token = _normalize_phrase(word)
    if not token or token.isdigit() or len(token) < 2:
        return False
    if any(char for char in word if char in "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụýỳỷỹỵ"):
        return True
    return token not in _english_terms(root=root)


def detect_vietnamese_words(prompt: str, root: Path | None = None) -> List[str]:
    tokens = [token for token in _WORD_RE.findall((prompt or "").lower()) if token]
    return [token for token in tokens if is_vietnamese_word(token, root=root)]


def normalize_prompt(prompt: str, root: Path | None = None) -> str:
    lookup, max_words = _lookup_table(root=root)
    tokens = [token for token in _WORD_RE.findall((prompt or "").lower()) if token and len(token) >= 2]
    normalized_tokens: List[str] = []
    index = 0

    while index < len(tokens):
        matched = False
        remaining = len(tokens) - index
        for size in range(min(max_words, remaining), 0, -1):
            phrase = " ".join(tokens[index : index + size])
            canonical = lookup.get(_normalize_phrase(phrase))
            if canonical:
                normalized_tokens.append(canonical)
                index += size
                matched = True
                break
        if matched:
            continue

        token = tokens[index]
        if token.isdigit() or len(token) < 2:
            index += 1
            continue
        if is_vietnamese_word(token, root=root):
            normalized_tokens.append(_normalize_phrase(token))
        else:
            normalized_tokens.append(_normalize_phrase(token))
        index += 1

    return " ".join(token for token in normalized_tokens if token)


def _ordered_feature_keywords(feature: Dict[str, Any], root: Path | None = None) -> List[str]:
    order: List[str] = []
    seen = set()
    fields: Sequence[Any] = (
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


def _extract_vietnamese_candidates(prompt: str, root: Path | None = None) -> List[str]:
    tokens = detect_vietnamese_words(prompt, root=root)
    lookup, _ = _lookup_table(root=root)
    candidates: List[str] = []
    seen = set()
    for token in tokens:
        if len(token) < 2 or token.isdigit():
            continue
        if not is_vietnamese_word(token, root=root):
            continue
        normalized = _normalize_phrase(token)
        if normalized and normalized not in seen and normalized not in lookup:
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
        for keyword in _ordered_feature_keywords(feature_data, root=root):
            if keyword and keyword not in primary_targets:
                primary_targets.append(keyword)

    target_pool = [keyword for keyword in primary_targets if keyword not in normalized_prompt_tokens]
    if not target_pool:
        target_pool = primary_targets[:]

    candidates = _extract_vietnamese_candidates(prompt, root=root)
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
