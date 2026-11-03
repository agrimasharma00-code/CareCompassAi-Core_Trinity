"""Build a small, traceable medicine-name lexicon from optional CSV data."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

FORM_TOKENS = re.compile(r"\b(?:tablet|tab|capsule|cap|syrup|injection|inj|suspension|drops?|cream|ointment|mg|mcg|g|ml|iu|%|oral)\b", re.I)
STRENGTH = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|%)\b", re.I)


def normalize_name(value: str) -> str:
    text = STRENGTH.sub(" ", str(value))
    text = FORM_TOKENS.sub(" ", text)
    text = re.sub(r"[()\[\]{}]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -_,.;").casefold()


def _find_column(columns, preferred: tuple[str, ...]) -> str | None:
    normalized = {str(column).strip().casefold(): str(column) for column in columns}
    for name in preferred:
        if name in normalized:
            return normalized[name]
    for column in columns:
        if any(name in str(column).casefold() for name in preferred):
            return str(column)
    return None


def build_lexicon(data_dir: str | Path, bd_rows: pd.DataFrame | None = None) -> list[dict[str, str]]:
    root = Path(data_dir)
    entries: dict[str, dict[str, str]] = {}
    for csv_path in root.rglob("*.csv") if root.exists() else []:
        try:
            frame = pd.read_csv(csv_path)
        except Exception:
            continue
        name_col = _find_column(frame.columns, ("name", "medicine_name", "brand_name", "brand"))
        if not name_col:
            continue
        c1 = _find_column(frame.columns, ("short_composition1", "composition", "salt"))
        c2 = _find_column(frame.columns, ("short_composition2",))
        for _, row in frame.iterrows():
            name = str(row.get(name_col, "")).strip()
            normalized = normalize_name(name)
            if not normalized or normalized == "nan":
                continue
            composition = " ".join(str(row.get(column, "")).strip() for column in (c1, c2) if column and pd.notna(row.get(column)) and str(row.get(column)).strip())
            entries.setdefault(normalized, {"name": name, "normalized": normalized, "composition": composition, "source": csv_path.name})
    if bd_rows is not None and not bd_rows.empty:
        for _, row in bd_rows.iterrows():
            for key in ("brand", "generic"):
                name = str(row.get(key, "")).strip()
                normalized = normalize_name(name)
                if normalized and normalized != "nan":
                    entries.setdefault(normalized, {"name": name, "normalized": normalized, "composition": str(row.get("generic", "")), "source": "prescription labels"})
    if not any(entry["source"] != "prescription labels" for entry in entries.values()):
        print("Warning: no A-Z medicine CSV found; the lexicon only contains labels from the prescription dataset.")
    return list(entries.values())


def save_lexicon(entries: list[dict[str, str]], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
