"""Care routing endpoint."""

from fastapi import APIRouter, Header

from app.core.pipeline import CarePipeline
from app.core.patient_records import apply_skin_priority
from app.api.intake_features import optional_patient_subject
from app.schemas.care import CareRequest, CareResponse


router = APIRouter(prefix="/api/v1/care", tags=["care"])
pipeline = CarePipeline()


@router.post("/intake-triage-match", response_model=CareResponse)
def intake_triage_match(request: CareRequest, authorization: str | None = Header(default=None)) -> CareResponse:
    response = pipeline.run(request)
    return apply_skin_priority(response, optional_patient_subject(authorization))
