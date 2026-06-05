"""Server-rendered dashboard pages (mobile-friendly)."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import config
from app.agents import REGISTRY
from app.agents.onboarding_agent import OnboardingAgent
from app.db import database
from app.orchestrator import approval
from app.remote import tunnel
from app.services import quota, revenue
from app.vault import vault
from app.web import auth

router = APIRouter()
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))
_onboarding = OnboardingAgent()


def _base_ctx(request: Request) -> dict:
    return {
        "request": request,
        "app_name": config.APP_NAME,
        "pending_count": approval.pending_count(),
    }


# --- auth pages ------------------------------------------------------------
@router.get("/healthz")
async def healthz():
    return {"ok": True}


@router.get("/set-pin", response_class=HTMLResponse)
async def set_pin_page(request: Request):
    if auth.is_pin_set():
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("set_pin.html", _base_ctx(request))


@router.post("/set-pin")
async def set_pin_submit(request: Request, pin: str = Form(...), confirm: str = Form(...)):
    ctx = _base_ctx(request)
    if len(pin) < 4:
        ctx["error"] = "Choose a PIN of at least 4 characters."
        return templates.TemplateResponse("set_pin.html", ctx)
    if pin != confirm:
        ctx["error"] = "The two entries didn't match."
        return templates.TemplateResponse("set_pin.html", ctx)
    auth.set_pin(pin)
    request.session["authed"] = True
    return RedirectResponse("/", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if not auth.is_pin_set():
        return RedirectResponse("/set-pin", status_code=303)
    return templates.TemplateResponse("login.html", _base_ctx(request))


@router.post("/login")
async def login_submit(request: Request, pin: str = Form(...)):
    if auth.verify_pin(pin):
        request.session["authed"] = True
        return RedirectResponse("/", status_code=303)
    ctx = _base_ctx(request)
    ctx["error"] = "Incorrect PIN."
    return templates.TemplateResponse("login.html", ctx)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# --- main pages ------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    ctx = _base_ctx(request)
    ctx.update({
        "agents": database.query("SELECT * FROM agents ORDER BY id"),
        "activity": database.query(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT 50"),
        "revenue": revenue.totals(),
        "quota": quota.snapshot(),
        "tunnel": tunnel.status(),
        "ready": _onboarding.overall_ready(),
    })
    return templates.TemplateResponse("dashboard.html", ctx)


@router.get("/approvals", response_class=HTMLResponse)
async def approvals_page(request: Request):
    ctx = _base_ctx(request)
    ctx["approvals"] = approval.list_pending()
    return templates.TemplateResponse("approvals.html", ctx)


@router.get("/revenue", response_class=HTMLResponse)
async def revenue_page(request: Request):
    ctx = _base_ctx(request)
    ctx.update({
        "totals": revenue.totals(),
        "by_stream": revenue.by_stream(),
        "recent": revenue.recent(),
    })
    return templates.TemplateResponse("revenue.html", ctx)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    ctx = _base_ctx(request)
    ctx.update({
        "steps": _onboarding.wizard_status(),
        "tunnel": tunnel.status(),
        "ready": _onboarding.overall_ready(),
    })
    return templates.TemplateResponse("settings.html", ctx)
