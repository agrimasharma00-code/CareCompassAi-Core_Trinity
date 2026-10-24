from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.care import router as care_router
from app.api.health import router as health_router
from app.api.sarvam_test import router as sarvam_router
from app.api.voice import router as voice_router
from app.modules.agents.router import router as assistant_router
from app.db.database import initialize_database
from app.api.auth import router as auth_router
from app.api.bookings import router as bookings_router
from app.api.live import router as live_router
from app.api.alerts import router as alerts_router
from app.api.checkins import router as checkins_router
from app.api.conversations import router as conversations_router
from app.api.wellness import router as wellness_router
app=FastAPI(title="CareCompass AI",description="Care routing only. Not diagnosis or prescription.",version="0.1.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
app.include_router(care_router);app.include_router(health_router);app.include_router(sarvam_router);app.include_router(voice_router);app.include_router(assistant_router);app.include_router(auth_router);app.include_router(bookings_router);app.include_router(live_router);app.include_router(alerts_router);app.include_router(checkins_router);app.include_router(conversations_router);app.include_router(wellness_router)


@app.on_event("startup")
def create_tables_and_seed_demo_accounts():
    initialize_database()
