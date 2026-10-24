from fastapi import APIRouter
from pathlib import Path
from app.integrations.sarvam_client import is_configured
router=APIRouter(tags=["health"])
@router.get("/health")
def health():
 p=Path(__file__).resolve().parents[2]/"models"/"triage.joblib"
 return {"status":"ok","model_loaded":p.exists(),"sarvam_configured":is_configured()}
