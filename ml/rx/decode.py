"""Greedy/prefix-beam CTC decoding and optional medicine lexicon ranking."""

from __future__ import annotations

from difflib import SequenceMatcher

import torch


def best_path(log_probs: torch.Tensor, charset: list[str]) -> tuple[str, float]:
    """Decode a [time, classes] log-probability matrix and return text/confidence."""
    probabilities = log_probs.exp()
    indexes = probabilities.argmax(dim=-1).tolist()
    output, scores, previous = [], [], None
    for step, index in enumerate(indexes):
        if index != 0 and index != previous and index < len(charset):
            output.append(charset[index])
            scores.append(float(probabilities[step, index]))
        previous = index
    return "".join(output).strip(), sum(scores) / max(1, len(scores))


def beam_search(log_probs: torch.Tensor, charset: list[str], beam_width: int = 10) -> list[tuple[str, float]]:
    """Small CTC prefix beam decoder; scores are log probabilities."""
    rows = log_probs.detach().cpu().tolist()
    beams: dict[tuple[int, ...], tuple[float, float]] = {(): (0.0, float("-inf"))}
    for row in rows:
        next_beams: dict[tuple[int, ...], tuple[float, float]] = {}
        for prefix, (blank_score, label_score) in beams.items():
            total = _logadd(blank_score, label_score)
            _merge(next_beams, prefix, blank_score=total + row[0])
            for label, score in enumerate(row[1:], start=1):
                if prefix and prefix[-1] == label:
                    _merge(next_beams, prefix, label_score=label_score + score)
                    _merge(next_beams, prefix + (label,), label_score=blank_score + score)
                else:
                    _merge(next_beams, prefix + (label,), label_score=total + score)
        beams = dict(sorted(next_beams.items(), key=lambda item: _logadd(*item[1]), reverse=True)[:beam_width])
    results = []
    for prefix, scores in sorted(beams.items(), key=lambda item: _logadd(*item[1]), reverse=True):
        results.append(("".join(charset[index] for index in prefix if index < len(charset)).strip(), _logadd(*scores)))
    return results


def _logadd(left: float, right: float) -> float:
    if left == float("-inf"):
        return right
    if right == float("-inf"):
        return left
    high = max(left, right)
    return high + torch.log1p(torch.exp(torch.tensor(min(left, right) - high))).item()


def _merge(beams: dict[tuple[int, ...], tuple[float, float]], key: tuple[int, ...], blank_score: float = float("-inf"), label_score: float = float("-inf")) -> None:
    old = beams.get(key, (float("-inf"), float("-inf")))
    beams[key] = (_logadd(old[0], blank_score), _logadd(old[1], label_score))


def lexicon_correct(text: str, lexicon: list[dict], k: int = 3) -> list[dict]:
    try:
        from rapidfuzz import fuzz
        score = lambda left, right: float(fuzz.WRatio(left, right))
    except ImportError:
        score = lambda left, right: 100.0 * SequenceMatcher(None, left, right).ratio()
    needle = "".join(char for char in text.casefold() if char.isalnum())
    ranked = []
    for item in lexicon:
        normalized = str(item.get("normalized") or "".join(char for char in str(item.get("name", "")).casefold() if char.isalnum()))
        value = score(needle, normalized)
        ranked.append({"name": item.get("name", normalized), "composition": item.get("composition", ""), "score": value, "source": item.get("source", "")})
    return sorted(ranked, key=lambda item: item["score"], reverse=True)[:k]
