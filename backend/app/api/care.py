from fastapi import APIRouter
from app.schemas.care import IntakeRequest,IntakeResponse
from app.core.pipeline import run
router=APIRouter(prefix="/api/v1/care",tags=["care"])
@router.post("/intake-triage-match",response_model=IntakeResponse)
def intake(request:IntakeRequest):return run(request)
