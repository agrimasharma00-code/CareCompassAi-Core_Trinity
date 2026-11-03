"""Character inventory and CTC encoding helpers for open-vocabulary RxRead."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

BLANK = "<blank>"


def build_charset(texts: Iterable[str], case_sensitive: bool = False) -> list[str]:
    values = [str(text) if case_sensitive else str(text).casefold() for text in texts]
    return [BLANK, *sorted({char for value in values for char in value if not char.isspace()}), " "]


def encode(text: str, charset: list[str], case_sensitive: bool = False) -> list[int]:
    normalized = str(text) if case_sensitive else str(text).casefold()
    indexes = {char: index for index, char in enumerate(charset) if index != 0}
    return [indexes[char] for char in normalized if char in indexes]


def save_charset(charset: list[str], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"blank_index": 0, "characters": charset}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_charset(path: str | Path) -> list[str]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return value["characters"] if isinstance(value, dict) else value
