"""Care routing endpoint."""

from fastapi import APIRouter

from app.core.pipeline import CarePipeline
from app.schemas.care import CareRequest, CareResponse


router = APIRouter(prefix="/api/v1/care", tags=["care"])
pipeline = CarePipeline()


@router.post("/intake-triage-match", response_model=CareResponse)
def intake_triage_match(request: CareRequest) -> CareResponse:
    return pipeline.run(request)
