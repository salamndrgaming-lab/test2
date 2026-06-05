"""WebSocket endpoint streaming the live activity feed to the dashboard."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.orchestrator import event_bus

router = APIRouter()


@router.websocket("/ws")
async def ws_feed(websocket: WebSocket) -> None:
    # Require the same PIN session as the rest of the dashboard.
    if not websocket.session.get("authed"):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    queue = event_bus.bus.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except (WebSocketDisconnect, asyncio.CancelledError, RuntimeError):
        pass
    finally:
        event_bus.bus.unsubscribe(queue)
