from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.care import router as care_router
from app.api.voice import router as voice_router
from app.api.realtime_voice import router as realtime_voice_router
from app.api.alerts import router as alerts_router
from app.api.auth import router as auth_router
from app.api.bookings import router as bookings_router
from app.api.ws import router as ws_router
from app.api.metrics import router as metrics_router


app = FastAPI(title="Niramaya API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # Browsers treat hostnames and ports as different origins. The local
    # frontend may use an alternate port when another dev server is running.
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ],
    # Explicitly allow browser preflight; sign-in POSTs use JSON and therefore
    # require an OPTIONS request before the browser sends credentials.
    allow_methods=["GET", "POST", "OPTIONS"],
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
