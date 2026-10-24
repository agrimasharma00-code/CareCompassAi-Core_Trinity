from fastapi import APIRouter, Query, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.db.database import SessionLocal
from app.db.models import User
from app.realtime import manager
from app.security import decode_access_token

router = APIRouter(tags=["live"])


@router.websocket("/ws")
async def live_updates(websocket: WebSocket, token: str | None = Query(default=None)):
    claims = decode_access_token(token or "")
    if not claims:
        await websocket.close(code=4401, reason="Login required")
        return
    try:
        user_id = int(claims["sub"])
    except (ValueError, TypeError):
        await websocket.close(code=4401, reason="Invalid login")
        return
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None or user.role != claims.get("role") or user.caregiver_id != claims.get("caregiver_id"):
            await websocket.close(code=4401, reason="Login is no longer valid")
            return
        await manager.connect(user.id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
