from fastapi import APIRouter
from app.integrations.sarvam_client import is_configured
router=APIRouter(prefix="/api/v1/sarvam",tags=["sarvam"])
@router.get("/ping")
def ping():return {"configured":is_configured()}
