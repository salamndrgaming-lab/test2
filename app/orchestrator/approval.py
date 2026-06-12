"""The human-in-the-loop approval gate — the heart of "no decision without me".

An agent that wants to publish/post/spend creates a PENDING approval and stops.
The action only runs when the user approves it in the dashboard, at which point the
registered resume-handler for that action_type is invoked. Pending rows persist
across restarts, so nothing public or money-related can fire unattended.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Awaitable, Callable

from app.db import database
from app.orchestrator import event_bus

# action_type -> async handler(approval_row: dict)
ResumeHandler = Callable[[dict], Awaitable[None]]
_handlers: dict[str, ResumeHandler] = {}


def register_handler(action_type: str, handler: ResumeHandler) -> None:
    _handlers[action_type] = handler


def create(
    agent: str,
    action_type: str,
    title: str,
    summary: str = "",
    payload: dict | None = None,
    preview_url: str | None = None,
) -> int:
    approval_id = database.execute(
        "INSERT INTO approvals (agent, action_type, title, summary, payload_json, preview_url) "
        "VALUES (?,?,?,?,?,?)",
        (agent, action_type, title, summary, json.dumps(payload or {}), preview_url),
    )
    event_bus.log(agent, f"Waiting for your approval: {title}", level="warn",
                  payload={"approval_id": approval_id, "action_type": action_type})
    event_bus.emit("approvals_changed")
    return approval_id


def get(approval_id: int) -> dict | None:
    row = database.query_one("SELECT * FROM approvals WHERE id=?", (approval_id,))
    if row and row.get("payload_json"):
        row["payload"] = json.loads(row["payload_json"])
    return row


def list_pending() -> list[dict]:
    rows = database.query(
        "SELECT * FROM approvals WHERE status='pending' ORDER BY created_at DESC"
    )
    for r in rows:
        r["payload"] = json.loads(r["payload_json"]) if r.get("payload_json") else {}
    return rows


def pending_count() -> int:
    row = database.query_one("SELECT COUNT(*) AS n FROM approvals WHERE status='pending'")
    return row["n"] if row else 0


async def resolve(approval_id: int, status: str, by: str = "you") -> dict | None:
    """Approve or reject. On approval, run the registered resume-handler."""
    row = get(approval_id)
    if not row or row["status"] != "pending":
        return row
    database.execute(
        "UPDATE approvals SET status=?, resolved_at=?, resolved_by=? WHERE id=?",
        (status, datetime.now(timezone.utc).isoformat(), by, approval_id),
    )
    event_bus.emit("approvals_changed")

    if status == "approved":
        event_bus.log(row["agent"], f"You approved: {row['title']}", level="success")
        handler = _handlers.get(row["action_type"])
        if handler:
            try:
                await handler(row)
            except Exception as exc:  # surface, never crash the request
                event_bus.log(row["agent"], f"Approved action failed: {exc}", level="error")
        else:
            event_bus.log(row["agent"],
                          f"No handler registered for '{row['action_type']}'.", level="warn")
    else:
        event_bus.log(row["agent"], f"You rejected: {row['title']}", level="info")
        # Negative signal: remember the rejection so the agent stops pitching
        # this direction (recalled alongside concepts in avoid-repeats prompts).
        from app.memory import memory
        memory.remember(row["agent"], f"REJECTED by owner: {row['title']}",
                        kind="learning", meta={"action_type": row["action_type"]})

    return get(approval_id)
