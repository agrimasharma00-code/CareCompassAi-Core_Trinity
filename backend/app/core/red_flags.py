"""Deterministic emergency screening. This is intentionally independent of ML."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "red_flags.json"
_PUNCTUATION = re.compile(r"[^\w\s\u0900-\u097f]", re.UNICODE)


def normalize_text(text: str) -> str:
    """Normalise simple spelling variants while retaining Devanagari text."""
    clean = _PUNCTUATION.sub(" ", text.lower())
    clean = re.sub(r"\b(sans|saan[s]?)\b", "saans", clean)
    clean = re.sub(r"\bdart\b", "dard", clean)
    return re.sub(r"\s+", " ", clean).strip()


@lru_cache
def load_red_flag_rules() -> tuple[dict[str, Any], ...]:
    with REGISTRY_PATH.open(encoding="utf-8") as handle:
        return tuple(json.load(handle))


def _is_negated(text: str, start: int, end: int) -> bool:
    """Check a short window before a match for English/Hinglish negation."""
    prefix = text[max(0, start - 36) : start].strip()
    suffix = text[end : end + 20].strip()
    before = re.search(r"(?:\bno|\bnot|\bwithout|\bnahi|\bnahin|नहीं)\s*(?:\w+\s*){0,3}$", prefix)
    after = re.match(r"(?:\bnahi|\bnahin|नहीं)(?:\s|$)", suffix)
    return bool(before or after)


def find_red_flags(text: str) -> list[str]:
    """Return labels for positive, non-negated registry matches."""
    normalized = normalize_text(text)
    fired: list[str] = []
    for rule in load_red_flag_rules():
        for raw_pattern in rule["patterns"]:
            pattern = normalize_text(raw_pattern)
            position = normalized.find(pattern)
            if position >= 0 and not _is_negated(normalized, position, position + len(pattern)):
                fired.append(rule["label"])
                break
    return fired
