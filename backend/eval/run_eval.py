"""Evaluate the saved routing pipeline without training on evaluation rows."""

import argparse
import csv
import json
import sys
from pathlib import Path

from sklearn.metrics import f1_score, recall_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.pipeline import CarePipeline  # noqa: E402
from app.core.loaders import load_vignettes  # noqa: E402
from app.schemas.care import CareRequest, CareResponse, Location  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vignettes", "--input", dest="vignettes", type=Path, help="Optional JSON or JSONL evaluation file. Defaults to supplied raw dataset.")
    parser.add_argument("--output", type=Path, default=ROOT / "eval" / "predictions.csv")
    args = parser.parse_args()
    if args.vignettes:
        source = args.vignettes
        if source.suffix == ".jsonl":
            rows = []
            for line in source.read_text(encoding="utf-8").splitlines():
                item = json.loads(line)
                if "request" in item and "response" in item:
                    from app.core.loaders import DATASET_CARE_TYPE_MAP, DATASET_URGENCY_MAP
                    care_type = DATASET_CARE_TYPE_MAP.get(item["response"].get("care_type"))
                    urgency = DATASET_URGENCY_MAP.get(item["response"].get("urgency"))
                    if care_type and urgency:
                        rows.append({"text": item["request"]["user_input"], "care_type": care_type, "urgency": urgency})
        else:
            rows = json.loads(source.read_text(encoding="utf-8"))
    else:
        rows = load_vignettes()
    pipeline = CarePipeline()
    predictions: list[dict[str, str]] = []
    for row in rows:
        response = pipeline.run(
            CareRequest(user_input=row["text"], location=Location(lat=28.545, lng=77.192)), force_final=True
        )
        CareResponse.model_validate(response)
        predictions.append(
            {
                "text": row["text"],
                "predicted_care_type": response.care_type.value if response.care_type else "",
                "predicted_urgency": response.urgency.value if response.urgency else "",
                "care_type": row.get("care_type", ""),
                "urgency": row.get("urgency", ""),
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    if all(row.get("care_type") and row.get("urgency") for row in rows):
        care_truth = [row["care_type"] for row in predictions]
        urgency_truth = [row["urgency"] for row in predictions]
        care_pred = [row["predicted_care_type"] for row in predictions]
        urgency_pred = [row["predicted_urgency"] for row in predictions]
        print(f"care_type macro-F1: {f1_score(care_truth, care_pred, average='macro', zero_division=0):.3f}")
        print(f"urgency macro-F1: {f1_score(urgency_truth, urgency_pred, average='macro', zero_division=0):.3f}")
        emergency_truth = [value == "immediate" for value in urgency_truth]
        emergency_pred = [value == "immediate" for value in urgency_pred]
        print(f"emergency recall: {recall_score(emergency_truth, emergency_pred, zero_division=0):.3f}")
        under_triage = sum(expected == "immediate" and actual != "immediate" for expected, actual in zip(urgency_truth, urgency_pred))
        print(f"under-triage count: {under_triage}")
    print(f"Wrote {len(predictions)} predictions to {args.output}")


if __name__ == "__main__":
    main()
