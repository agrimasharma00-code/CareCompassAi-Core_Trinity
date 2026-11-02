import json
from fastapi import APIRouter, HTTPException
from pathlib import Path
from app.integrations.sarvam_client import is_configured
from app.db.database import engine
from sqlalchemy import inspect
router=APIRouter(tags=["health"])
@router.get("/health")
def health():
 p=Path(__file__).resolve().parents[2]/"models"/"triage.joblib"
 try:
  database_ready = bool(inspect(engine).get_table_names())
 except Exception:
  database_ready = False
 return {"status":"ok" if database_ready and p.exists() else "degraded","model_loaded":p.exists(),"database_initialized":database_ready,"sarvam_configured":is_configured(),"subsystems":{"model":"ready" if p.exists() else "missing","database":"ready" if database_ready else "unavailable","sarvam":"configured" if is_configured() else "not_configured"}}

@router.get("/api/v1/metrics")
def metrics():
 path=Path(__file__).resolve().parents[2]/"data"/"metrics.json"
 if not path.exists(): raise HTTPException(status_code=404,detail="Training metrics are not available yet. Run ml/train_triage.py.")
 return json.loads(path.read_text(encoding="utf-8"))
