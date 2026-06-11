"""JSON API: approvals, agent control, secrets, brain test, and live state."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from app import agents, config
from app.brain import router as brain
from app.brain.errors import BrainError
from app.orchestrator import approval
from app.remote import tunnel
from app.services import quota, revenue
from app.vault import vault

router = APIRouter(prefix="/api")


@router.get("/state")
async def state():
    return {
        "agents": {a["name"]: {"enabled": bool(a["enabled"]), "status": a["status"],
                               "last_run_at": a["last_run_at"],
                               "last_message": _last_messages().get(a["name"])}
                   for a in _agents_rows()},
        "pending_count": approval.pending_count(),
        "revenue": revenue.totals(),
        "quota": quota.snapshot(),
        "tunnel": tunnel.status(),
    }


def _agents_rows():
    from app.db import database
    return database.query("SELECT * FROM agents ORDER BY id")


def _last_messages() -> dict:
    """Latest activity message per agent, so the Vault view can seed speech bubbles."""
    from app.db import database
    rows = database.query(
        "SELECT agent, message FROM activity_log "
        "WHERE id IN (SELECT MAX(id) FROM activity_log GROUP BY agent)")
    return {r["agent"]: r["message"] for r in rows}


# --- secrets (onboarding) --------------------------------------------------
@router.post("/secret")
async def save_secret(key: str = Body(...), value: str = Body(...)):
    if key not in config.SECRET_KEYS:
        return JSONResponse({"error": "Unknown key"}, status_code=400)
    value = value.strip()
    if not value:
        return JSONResponse({"error": "Value is empty"}, status_code=400)
    vault.set_secret(key, value)
    return {"ok": True, "key": key, "connected": True}


@router.delete("/secret/{key}")
async def delete_secret(key: str):
    vault.delete_secret(key)
    return {"ok": True, "key": key, "connected": False}


# --- approvals -------------------------------------------------------------
@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: int):
    row = await approval.resolve(approval_id, "approved")
    return {"ok": True, "approval": row}


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: int):
    row = await approval.resolve(approval_id, "rejected")
    return {"ok": True, "approval": row}


# --- agents ----------------------------------------------------------------
@router.post("/agents/{name}/toggle")
async def toggle_agent(name: str, enabled: bool = Body(..., embed=True)):
    agent = agents.get(name)
    if not agent:
        return JSONResponse({"error": "Unknown agent"}, status_code=404)
    agent.set_enabled(enabled)
    return {"ok": True, "name": name, "enabled": enabled}


@router.post("/agents/{name}/run")
async def run_agent(name: str):
    agent = agents.get(name)
    if not agent:
        return JSONResponse({"error": "Unknown agent"}, status_code=404)
    # Run in the background so the dashboard stays responsive.
    asyncio.create_task(agent.tick(forced=True))
    return {"ok": True, "name": name, "started": True}


# --- honest manual revenue (Etsy/KDP/YouTube have no easy read API) --------
@router.post("/revenue/manual")
async def add_manual_revenue(amount: float = Body(...), label: str = Body("Manual entry"),
                             fees: float = Body(0.0), occurred_at: str = Body(None)):
    """Record a REAL sale you copied from a payout dashboard. Tagged source='manual'
    and visually distinguished from API-synced sales; the bookkeeper never writes these."""
    import datetime
    import uuid
    from app.db import database
    from app.orchestrator import event_bus
    try:
        amount = float(amount)
        fees = float(fees or 0)
    except (TypeError, ValueError):
        return JSONResponse({"error": "Amount and fees must be numbers"}, status_code=400)
    if amount <= 0:
        return JSONResponse({"error": "Enter an amount greater than 0"}, status_code=400)
    occ = (occurred_at or datetime.date.today().isoformat())
    database.execute(
        "INSERT INTO sales (product_id, platform, external_id, gross_amount, fees, "
        "net_amount, occurred_at, source) VALUES (NULL,?,?,?,?,?,?, 'manual')",
        ((label or "Manual entry")[:60], "manual:" + uuid.uuid4().hex,
         amount, fees, round(amount - fees, 2), occ))
    event_bus.emit("revenue_changed")
    return {"ok": True}


@router.delete("/revenue/manual/{sale_id}")
async def delete_manual_revenue(sale_id: int):
    from app.db import database
    from app.orchestrator import event_bus
    database.execute("DELETE FROM sales WHERE id=? AND source='manual'", (sale_id,))
    event_bus.emit("revenue_changed")
    return {"ok": True}


# --- blog / audience exports (free hosting + your own email tool) ----------
@router.post("/blog/export")
async def blog_export_endpoint():
    from app.services import blog_export
    path, count = blog_export.export()
    return {"ok": True, "count": count, "path": str(path),
            "hint": "Drag this folder onto app.netlify.com/drop, or commit it to a "
                    "GitHub Pages repo, to publish your blog for free."}


@router.post("/subscribers/export")
async def subscribers_export():
    import csv
    from app.db import database
    rows = database.query("SELECT email, created_at FROM email_subscribers ORDER BY id")
    out = config.DATA_DIR / "subscribers.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["email", "subscribed_at"])
        for r in rows:
            w.writerow([r["email"], r["created_at"]])
    return {"ok": True, "count": len(rows), "path": str(out)}


# --- brain test (used by the onboarding wizard) ----------------------------
@router.post("/brain/test")
async def brain_test(prompt: str = Body("Say hello in one short sentence.", embed=True),
                     provider: str | None = Body(None, embed=True)):
    """Test the brain. `provider` ("gemini"/"groq") forces one, so the user can
    confirm the backup works; omitted = normal failover routing."""
    try:
        used, reply = await brain.generate_detailed(prompt, task="bulk", only=provider)
        return {"ok": True, "reply": reply, "provider": used}
    except BrainError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
