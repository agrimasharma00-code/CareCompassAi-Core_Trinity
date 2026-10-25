"""Small, explicit loaders for the file-backed prototype data."""

import json
import csv
from functools import lru_cache
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RAW_DATA_DIR = DATA_DIR / "raw"

DATASET_CARE_TYPE_MAP = {
    "paramedic_home_visit": "paramedic_home_visit",
    "home_nursing": "nurse",
    "lab_test_home": "lab_test_home",
    "teleconsultation": "gp_teleconsult",
    "emergency_112": "emergency_referral",
}
DATASET_URGENCY_MAP = {"emergency": "immediate", "same_day": "same_day", "scheduled": "routine"}


@lru_cache
def load_dataset() -> tuple[dict[str, Any], ...]:
    """Return raw dataset-contract rows for augmentation and evaluation helpers."""
    dataset = RAW_DATA_DIR / "triage_dataset.jsonl"
    if not dataset.exists():
        return ()
    with dataset.open(encoding="utf-8") as handle:
        return tuple(json.loads(line) for line in handle if line.strip())


def _load_json(filename: str) -> Any:
    with (DATA_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache
def load_caregivers() -> list[dict[str, Any]]:
    """Load the supplied roster, normalised for the transparent matcher."""
    roster = RAW_DATA_DIR / "caregivers.csv"
    if not roster.exists():
        return _load_json("sample_caregivers.json")
    role_map = {
        "medic": ("paramedic_home_visit", "nurse"),
        "doctor": ("gp_teleconsult", "specialist"),
        "phlebotomist": ("lab_test_home",),
    }
    with roster.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        {
            "id": row["caregiver_id"],
            "name": row["name"],
            "role": row["role"],
            "qualification": row["qualification"],
            "gender": row["gender"],
            "base_area": row["base_area"],
            "experience_years": int(row["experience_years"]),
            "care_types": role_map.get(row["role"], ()),
            "languages": [_normalise_language(value) for value in row["languages"].split(";")],
            "skills": row["skills"].split(";"),
            "lat": float(row["base_lat"]),
            "lng": float(row["base_lng"]),
            "max_radius_km": float(row["max_radius_km"]),
            "rating": float(row["rating"]),
            "available_slots": [f"{row['free_from']}–{row['free_until']}"],
            "active": row["active"].strip().lower() == "true",
        }
        for row in rows
        if row.get("active", "").strip().lower() == "true"
    ]


def public_caregiver_profiles(caregiver_ids: list[str]) -> list[dict[str, Any]]:
    """Return human-readable roster details in the matcher's ranked order."""
    roster_by_id = {caregiver["id"]: caregiver for caregiver in load_caregivers()}
    return [
        {
            "caregiver_id": caregiver["id"],
            "name": caregiver["name"],
            "role": caregiver["role"],
            "qualification": caregiver["qualification"],
            "rating": caregiver["rating"],
            "experience_years": caregiver["experience_years"],
            "base_area": caregiver["base_area"],
        }
        for caregiver_id in caregiver_ids
        if (caregiver := roster_by_id.get(caregiver_id)) is not None
    ]


@lru_cache
def load_vignettes() -> list[dict[str, Any]]:
    """Load trainable, labelled turns from the supplied JSONL dataset."""
    dataset = RAW_DATA_DIR / "triage_dataset.jsonl"
    if not dataset.exists():
        return _load_json("sample_vignettes.json")
    vignettes: list[dict[str, Any]] = []
    with dataset.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            response = row["response"]
            care_type = DATASET_CARE_TYPE_MAP.get(response.get("care_type"))
            urgency = DATASET_URGENCY_MAP.get(response.get("urgency"))
            if care_type and urgency:
                vignettes.append({"text": row["request"]["user_input"], "care_type": care_type, "urgency": urgency})
    return vignettes


@lru_cache
def load_multi_turn_examples() -> list[dict[str, Any]]:
    """Expose supplied multi-turn examples for evaluation and conversation tests."""
    path = RAW_DATA_DIR / "multi_turn_examples.jsonl"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _normalise_language(value: str) -> str:
    normalised = value.strip().lower()
    return {"hindi": "hi", "english": "en", "hinglish": "hinglish"}.get(normalised, normalised)


@lru_cache
def load_taxonomy() -> dict[str, Any]:
    return _load_json("care_taxonomy.json")
