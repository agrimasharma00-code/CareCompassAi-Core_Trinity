"""WebSocket fan-out for demo booking and ambulance status updates."""

from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter(prefix="/api/v1/ws", tags=["live-updates"])


class Hub:
    def __init__(self) -> None:
        self.clients: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, channel: str, socket: WebSocket) -> None:
        await socket.accept(); self.clients[channel].add(socket)

    async def publish(self, channel: str, event: dict[str, object]) -> None:
        disconnected: list[WebSocket] = []
        for socket in self.clients[channel]:
            try: await socket.send_json(event)
            except Exception: disconnected.append(socket)
        for socket in disconnected: self.clients[channel].discard(socket)


hub = Hub()


async def _stream(channel: str, socket: WebSocket) -> None:
    await hub.connect(channel, socket)
    try:
        while True: await socket.receive_text()
    except WebSocketDisconnect:
        hub.clients[channel].discard(socket)


@router.websocket("/dispatch")
async def dispatch_updates(socket: WebSocket) -> None:
    await _stream("dispatch", socket)


@router.websocket("/provider")
async def provider_updates(socket: WebSocket) -> None:
    await _stream("provider", socket)


@router.websocket("/patient/{booking_id}")
async def patient_updates(booking_id: str, socket: WebSocket) -> None:
    await _stream(f"patient:{booking_id}", socket)
