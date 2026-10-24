import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.api.care import router as care_router
from app.api.voice import router as voice_router
from app.api.realtime_voice import router as realtime_voice_router
from app.api.alerts import router as alerts_router
from app.api.auth import router as auth_router
from app.api.bookings import router as bookings_router
from app.api.ws import router as ws_router
from app.api.metrics import router as metrics_router
from app.config import PROJECT_ROOT


load_dotenv(PROJECT_ROOT / ".env")
PHONE_PATTERN = re.compile(r"^\+\d{7,15}$")
STATIC_DIR = Path(__file__).resolve().parent / "static"


class CallRequest(BaseModel):
    to: str
    bridge_to: str | None = None


def _valid_phone(number: str | None) -> bool:
    return bool(number and PHONE_PATTERN.fullmatch(number))


def _twilio_client() -> Client:
    account_sid = os.getenv("twilio_account_sid")
    auth_token = os.getenv("twilio_auth_token")
    if not account_sid or not auth_token:
        raise HTTPException(status_code=503, detail="Twilio credentials are not configured.")
    return Client(account_sid, auth_token)


app = FastAPI(title="CareCompass API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # Browsers treat localhost and 127.0.0.1 as different origins.
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(care_router)
app.include_router(voice_router)
app.include_router(realtime_voice_router)
app.include_router(auth_router)
app.include_router(bookings_router)
app.include_router(alerts_router)
app.include_router(ws_router)
app.include_router(metrics_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def twilio_demo_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/config")
def call_config() -> dict[str, str]:
    """Expose only safe, non-secret call defaults to the standalone UI."""
    return {"default_to": os.getenv("DEFAULT_TO", ""), "bridge_to": os.getenv("BRIDGE_TO", "")}


@app.post("/call")
def create_call(request: CallRequest) -> dict[str, str | int]:
    if not _valid_phone(request.to):
        raise HTTPException(status_code=400, detail="Use an E.164 phone number, for example +14155552671.")
    if request.bridge_to and not _valid_phone(request.bridge_to):
        raise HTTPException(status_code=400, detail="Bridge number must use E.164 format.")
    twiml = (
        f"<Response><Say>Connecting you now.</Say><Dial>{request.bridge_to}</Dial></Response>"
        if request.bridge_to
        else "<Response><Say>Hello, this is a demo call from your app.</Say></Response>"
    )
    try:
        call = _twilio_client().calls.create(to=request.to, from_=os.getenv("TWILIO_NUMBER", ""), twiml=twiml)
        return {"sid": call.sid, "status": call.status}
    except TwilioRestException as error:
        raise HTTPException(status_code=400, detail={"error": error.msg, "code": error.code}) from error


@app.get("/call/{sid}")
def call_status(sid: str) -> dict[str, str]:
    try:
        call = _twilio_client().calls(sid).fetch()
        return {"sid": call.sid, "status": call.status}
    except TwilioRestException as error:
        raise HTTPException(status_code=400, detail={"error": error.msg, "code": error.code}) from error
