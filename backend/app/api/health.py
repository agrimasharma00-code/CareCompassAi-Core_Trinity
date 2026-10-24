import json
from fastapi import APIRouter, HTTPException
from pathlib import Path
from app.integrations.sarvam_client import is_configured
router=APIRouter(tags=["health"])
@router.get("/health")
def health():
 p=Path(__file__).resolve().parents[2]/"models"/"triage.joblib"
 return {"status":"ok","model_loaded":p.exists(),"sarvam_configured":is_configured()}

@router.get("/api/v1/metrics")
def metrics():
 path=Path(__file__).resolve().parents[2]/"data"/"metrics.json"
 if not path.exists(): raise HTTPException(status_code=404,detail="Training metrics are not available yet. Run ml/train_triage.py.")
 return json.loads(path.read_text(encoding="utf-8"))
