from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.care import router as care_router
from app.api.health import router as health_router
from app.api.sarvam_test import router as sarvam_router
from app.api.voice import router as voice_router
from app.modules.agents.router import router as assistant_router
app=FastAPI(title="CareCompass AI",description="Care routing only. Not diagnosis or prescription.",version="0.1.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
app.include_router(care_router);app.include_router(health_router);app.include_router(sarvam_router);app.include_router(voice_router);app.include_router(assistant_router)
