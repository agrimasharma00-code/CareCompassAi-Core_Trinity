"""Read only, judge-facing validation metrics computed by the training script."""

import json
from pathlib import Path

from fastapi import APIRouter

from app.core.loaders import load_caregivers, load_vignettes


router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])
METRICS_PATH = Path(__file__).resolve().parents[2] / "models" / "metrics.json"


@router.get("")
def metrics() -> dict[str, object]:
    computed = json.loads(METRICS_PATH.read_text(encoding="utf-8")) if METRICS_PATH.exists() else None
    return {"computed": computed, "training_records": len(load_vignettes()), "active_caregivers": len(load_caregivers()), "note": "Metrics are computed only by the local training run; no hidden test data is used."}
