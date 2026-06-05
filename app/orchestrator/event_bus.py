"""In-process pub/sub powering the dashboard's live activity feed.

Agents run in the asyncio loop (and occasionally background threads), so publish()
is made thread-safe by hopping back onto the main loop when needed. Every event is
also persisted to `activity_log` so the feed survives a page refresh / restart.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from app.db import database


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _dispatch(self, event: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow client; drop rather than block the producer

    def publish(self, event: dict) -> None:
        if self._loop and self._loop.is_running():
            try:
                self._loop.call_soon_threadsafe(self._dispatch, event)
                return
            except RuntimeError:
                pass
        self._dispatch(event)


bus = EventBus()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(agent: str, message: str, level: str = "info", payload: dict | None = None) -> None:
    """Record an agent action and stream it to the dashboard."""
    database.execute(
        "INSERT INTO activity_log (agent, level, message, payload_json) VALUES (?,?,?,?)",
        (agent, level, message, json.dumps(payload) if payload else None),
    )
    bus.publish({
        "type": "activity",
        "agent": agent,
        "level": level,
        "message": message,
        "payload": payload,
        "created_at": _now(),
    })


def emit(event_type: str, **fields) -> None:
    """Publish a non-activity UI event (e.g. approvals/revenue changed)."""
    bus.publish({"type": event_type, "created_at": _now(), **fields})
