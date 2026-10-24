"""Small, explicit loaders for the file-backed prototype data."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load_json(filename: str) -> Any:
    with (DATA_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache
def load_caregivers() -> list[dict[str, Any]]:
    """Return synthetic prototype caregiver profiles."""
    return _load_json("sample_caregivers.json")


@lru_cache
def load_vignettes() -> list[dict[str, Any]]:
    return _load_json("sample_vignettes.json")


@lru_cache
def load_taxonomy() -> dict[str, Any]:
    return _load_json("care_taxonomy.json")
