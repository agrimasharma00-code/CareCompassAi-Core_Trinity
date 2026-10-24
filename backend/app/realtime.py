import asyncio
import logging
from collections import defaultdict
from concurrent.futures import TimeoutError as FutureTimeout

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """In-memory WebSocket connections keyed by authenticated user ID."""

    def __init__(self):
        self.connections: dict[int, set[WebSocket]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.loop = asyncio.get_running_loop()
        self.connections[user_id].add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        sockets = self.connections.get(user_id)
        if sockets:
            sockets.discard(websocket)
            if not sockets:
                self.connections.pop(user_id, None)

    async def publish(self, user_ids: list[int], message: dict) -> None:
        stale: list[tuple[int, WebSocket]] = []
        for user_id in set(user_ids):
            for websocket in tuple(self.connections.get(user_id, ())):
                try:
                    await websocket.send_json(message)
                except (RuntimeError, OSError, WebSocketDisconnect):
                    stale.append((user_id, websocket))
        for user_id, websocket in stale:
            self.disconnect(user_id, websocket)

    def publish_from_sync(self, user_ids: list[int], message: dict) -> None:
        loop = self.loop
        if loop is None or not loop.is_running():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.publish(user_ids, message), loop).result(timeout=3)
        except FutureTimeout:
            logger.warning("WebSocket update timed out for an application event")
        except RuntimeError:
            logger.warning("WebSocket update could not be delivered to connected users")


manager = ConnectionManager()
