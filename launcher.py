"""Double-click entry point for AI Income Team.

Starts the local web server, opens your browser to the dashboard, and keeps a
single instance running. No command-line knowledge required — running this file
(or the packaged Start app) is all that's needed.
"""
from __future__ import annotations

import socket
import threading
import webbrowser

import uvicorn

from app import config

# Single-instance guard: hold a localhost socket so a second launch can detect us.
_GUARD_PORT = config.PORT + 1


def _already_running() -> bool:
    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    guard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        guard.bind(("127.0.0.1", _GUARD_PORT))
    except OSError:
        return True
    # Keep the socket open for the life of the process.
    _already_running._guard = guard  # type: ignore[attr-defined]
    return False


def _open_browser() -> None:
    threading.Timer(1.5, lambda: webbrowser.open(f"http://{config.HOST}:{config.PORT}")).start()


def main() -> None:
    if _already_running():
        webbrowser.open(f"http://{config.HOST}:{config.PORT}")
        print("AI Income Team is already running — opened it in your browser.")
        return
    print(f"Starting {config.APP_NAME} … your browser will open shortly.")
    print(f"If it doesn't, go to:  http://{config.HOST}:{config.PORT}")
    _open_browser()
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
