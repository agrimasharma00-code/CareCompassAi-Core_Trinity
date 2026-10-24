from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.care import router as care_router
from app.api.voice import router as voice_router
from app.api.realtime_voice import router as realtime_voice_router


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
