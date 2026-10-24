"""Train the deliberately small, fast baseline triage models."""

import sys
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.core.loaders import load_vignettes  # noqa: E402


def make_model() -> Pipeline:
    features = FeatureUnion(
        [
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)),
            ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ]
    )
    return Pipeline([("features", features), ("classifier", LogisticRegression(class_weight="balanced", max_iter=1000))])


def main() -> None:
    rows = load_vignettes()
    texts = [row["text"] for row in rows]
    care_labels = [row["care_type"] for row in rows]
    urgency_labels = [row["urgency"] for row in rows]
    train_indices, validation_indices = train_test_split(
        range(len(rows)), test_size=0.5, random_state=42, stratify=care_labels
    )
    train_indices, validation_indices = list(train_indices), list(validation_indices)
    train_texts = [texts[index] for index in train_indices]
    validation_texts = [texts[index] for index in validation_indices]

    care_model, urgency_model = make_model(), make_model()
    care_model.fit(train_texts, [care_labels[index] for index in train_indices])
    urgency_model.fit(train_texts, [urgency_labels[index] for index in train_indices])
    care_truth = [care_labels[index] for index in validation_indices]
    urgency_truth = [urgency_labels[index] for index in validation_indices]
    care_pred = care_model.predict(validation_texts)
    urgency_pred = urgency_model.predict(validation_texts)
    immediate_probs = urgency_model.predict_proba(validation_texts)
    urgency_with_bias = [
        "immediate" if probability[list(urgency_model.classes_).index("immediate")] >= settings.immediate_threshold else predicted
        for probability, predicted in zip(immediate_probs, urgency_pred)
    ]

    print(f"care_type macro-F1: {f1_score(care_truth, care_pred, average='macro', zero_division=0):.3f}")
    print(f"urgency macro-F1: {f1_score(urgency_truth, urgency_pred, average='macro', zero_division=0):.3f}")
    print("care_type confusion matrix:")
    print(confusion_matrix(care_truth, care_pred))
    print("urgency confusion matrix:")
    print(confusion_matrix(urgency_truth, urgency_pred))
    emergency_truth = [value == "immediate" for value in urgency_truth]
    emergency_pred = [value == "immediate" for value in urgency_with_bias]
    baseline_emergency_pred = [value == "immediate" for value in urgency_pred]
    print(f"emergency recall before threshold bias: {recall_score(emergency_truth, baseline_emergency_pred, zero_division=0):.3f}")
    print(f"emergency recall at threshold {settings.immediate_threshold:.2f}: {recall_score(emergency_truth, emergency_pred, zero_division=0):.3f}")

    models_dir = Path(__file__).resolve().parents[1] / "models"
    models_dir.mkdir(exist_ok=True)
    joblib.dump(care_model, models_dir / "care_type.joblib")
    joblib.dump(urgency_model, models_dir / "urgency.joblib")


if __name__ == "__main__":
    main()
