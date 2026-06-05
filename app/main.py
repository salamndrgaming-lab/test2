"""FastAPI application factory: wires together the engine and the dashboard.

One process hosts everything — the web UI, the JSON API, the live websocket feed,
the background scheduler, and the secure tunnel.
"""
from __future__ import annotations

import asyncio
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import config
from app.agents import register_all_handlers
from app.db import database
from app.orchestrator import event_bus, scheduler
from app.remote import tunnel
from app.web import auth
from app.web import routes_api, routes_dashboard, ws


def _session_secret() -> str:
    secret = database.get_setting("session_secret")
    if not secret:
        secret = secrets.token_hex(32)
        database.set_setting("session_secret", secret)
    return secret


def create_app() -> FastAPI:
    config.ensure_dirs()
    database.init_db()

    app = FastAPI(title=config.APP_NAME)

    # Static assets and generated previews (design images, etc.).
    app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
    app.mount("/generated", StaticFiles(directory=str(config.GENERATED_DIR)), name="generated")

    # NOTE on ordering: middleware added LAST runs OUTERMOST. The PIN gate reads
    # request.session, so SessionMiddleware must wrap it — i.e. be added AFTER.
    @app.middleware("http")
    async def require_pin(request: Request, call_next):
        path = request.url.path
        if auth.is_public(path) or path.startswith(("/static/", "/generated/")):
            return await call_next(request)
        if not auth.is_pin_set():
            return RedirectResponse("/set-pin", status_code=303)
        if not auth.is_authed(request):
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)

    app.add_middleware(SessionMiddleware, secret_key=_session_secret(),
                       same_site="lax", max_age=60 * 60 * 24 * 30)

    app.include_router(routes_dashboard.router)
    app.include_router(routes_api.router)
    app.include_router(ws.router)

    @app.on_event("startup")
    async def _startup():
        event_bus.bus.attach_loop(asyncio.get_running_loop())
        register_all_handlers()
        scheduler.start()
        if os.environ.get("AIT_NO_TUNNEL") != "1":
            tunnel.start()
        event_bus.log("system", f"{config.APP_NAME} is up and running.", level="success")

    @app.on_event("shutdown")
    async def _shutdown():
        scheduler.shutdown()
        tunnel.stop()

    return app


app = create_app()
