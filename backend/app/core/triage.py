"""Baseline classifier wrapper with a safe deterministic fallback."""

from dataclasses import dataclass
from pathlib import Path

import joblib

from app.config import settings


MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


@dataclass(frozen=True)
class TriageResult:
    care_type: str
    urgency: str
    confidence: float
    urgency_probability: float


def _fallback(text: str) -> TriageResult:
    lower = text.lower()
    if any(word in lower for word in ("nurse", "dressing", "wound")):
        return TriageResult("nurse", "routine", 0.55, 0.05)
    if any(word in lower for word in ("sample collection", "blood sample", "lab test", "blood test")):
        return TriageResult("lab_test_home", "routine", 0.55, 0.05)
    if any(word in lower for word in ("home visit", "vitals")):
        return TriageResult("paramedic_home_visit", "same_day", 0.55, 0.12)
    if any(word in lower for word in ("skin", "diabetes", "joint")):
        return TriageResult("specialist", "routine", 0.55, 0.05)
    return TriageResult("gp_teleconsult", "same_day", 0.45, 0.16)


class TriageClassifier:
    def __init__(self) -> None:
        self.care_model = None
        self.urgency_model = None
        care_path = MODELS_DIR / "care_type.joblib"
        urgency_path = MODELS_DIR / "urgency.joblib"
        if care_path.exists() and urgency_path.exists():
            self.care_model = joblib.load(care_path)
            self.urgency_model = joblib.load(urgency_path)

    def predict(self, text: str) -> TriageResult:
        if self.care_model is None or self.urgency_model is None:
            return _fallback(text)
        care_probs = self.care_model.predict_proba([text])[0]
        urgency_probs = self.urgency_model.predict_proba([text])[0]
        care_index = care_probs.argmax()
        urgency_index = urgency_probs.argmax()
        care_type = str(self.care_model.classes_[care_index])
        urgency = str(self.urgency_model.classes_[urgency_index])
        immediate_probability = _class_probability(self.urgency_model, urgency_probs, "immediate")
        if immediate_probability >= settings.immediate_threshold:
            urgency = "immediate"
        return TriageResult(care_type, urgency, float(care_probs[care_index]), immediate_probability)


def _class_probability(model: object, probabilities: object, label: str) -> float:
    classes = list(getattr(model, "classes_"))
    return float(probabilities[classes.index(label)]) if label in classes else 0.0
