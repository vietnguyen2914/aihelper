from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

try:
    from .common import helper_root, safe_load_json, tokenize
except ImportError:
    from common import helper_root, safe_load_json, tokenize


_PHRASE_SPLIT_RE = re.compile(r"[^0-9a-zA-ZÀ-ỹ]+")
_VIETNAMESE_FILLER_WORDS = {
    "bi",
    "bị",
    "cho",
    "cua",
    "của",
    "khi",
    "la",
    "là",
    "len",
    "lên",
    "tren",
    "trên",
    "tu",
    "từ",
    "va",
    "và",
    "voi",
    "với",
}


def _synonyms_path() -> Path:
    return helper_root() / "context_engine" / "synonyms.json"


def remove_accents(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _phrase_tokens(text: str) -> List[str]:
    cleaned = _PHRASE_SPLIT_RE.sub(" ", (text or "").lower()).strip()
    if not cleaned:
        return []
    return [token for token in cleaned.split() if token]


def _clean_phrase(text: str) -> str:
    return " ".join(_phrase_tokens(text))


@lru_cache(maxsize=1)
def _synonyms() -> Dict[str, List[str]]:
    data = safe_load_json(_synonyms_path(), default={})
    if not isinstance(data, dict):
        return {}

    normalized: Dict[str, List[str]] = {}
    for canonical, values in data.items():
        if not isinstance(canonical, str):
            continue
        normalized_canonical = _clean_phrase(canonical)
        if not normalized_canonical:
            continue
        phrases = [canonical]
        if isinstance(values, list):
            phrases.extend(str(value) for value in values if isinstance(value, str))

        deduped: List[str] = []
        seen = set()
        for phrase in phrases:
            cleaned = _clean_phrase(phrase)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        normalized[normalized_canonical] = deduped
    return normalized


@lru_cache(maxsize=1)
def _phrase_lookup() -> Tuple[Dict[str, str], int]:
    lookup: Dict[str, str] = {}
    max_words = 1
    for canonical, phrases in _synonyms().items():
        for phrase in phrases:
            for variant in {phrase, remove_accents(phrase)}:
                cleaned = _clean_phrase(variant)
                if not cleaned:
                    continue
                lookup[cleaned] = canonical
                max_words = max(max_words, len(cleaned.split()))
    return lookup, max_words


def normalize_prompt(prompt: str) -> str:
    lookup, max_words = _phrase_lookup()
    tokens = _phrase_tokens(prompt)
    normalized_tokens: List[str] = []
    index = 0

    while index < len(tokens):
        matched = False
        remaining = len(tokens) - index
        for size in range(min(max_words, remaining), 0, -1):
            phrase = " ".join(tokens[index : index + size])
            canonical = lookup.get(phrase) or lookup.get(_clean_phrase(remove_accents(phrase)))
            if canonical:
                normalized_tokens.extend(canonical.split())
                index += size
                matched = True
                break

        if matched:
            continue

        stripped = remove_accents(tokens[index]).lower()
        if stripped and stripped not in _VIETNAMESE_FILLER_WORDS:
            normalized_tokens.append(stripped)
        index += 1

    return " ".join(normalized_tokens)


def expand_keywords(feature_keywords: Sequence[str] | Iterable[str]) -> List[str]:
    expanded: List[str] = []
    seen = set()
    synonyms = _synonyms()

    for keyword in feature_keywords:
        if not isinstance(keyword, str):
            continue
        canonical_keyword = normalize_prompt(keyword)
        if not canonical_keyword:
            continue

        phrases = [canonical_keyword]
        phrases.extend(synonyms.get(canonical_keyword, []))
        for phrase in phrases:
            cleaned = _clean_phrase(phrase)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                expanded.append(cleaned)
    return expanded


def multilingual_tokens(text: str) -> Set[str]:
    return set(tokenize(normalize_prompt(text)))
