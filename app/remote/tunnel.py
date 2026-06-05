"""Secure phone access via a free Cloudflare quick tunnel.

If the bundled/installed `cloudflared` binary is present, we start a quick tunnel
(`cloudflared tunnel --url http://127.0.0.1:PORT`) and capture the public https URL
it prints. The whole dashboard sits behind a PIN, so the URL is safe to use on your
phone. If cloudflared isn't available, we degrade gracefully to same-wifi (LAN) access.
"""
from __future__ import annotations

import re
import shutil
import socket
import subprocess
import threading

from app import config
from app.db import database
from app.orchestrator import event_bus

_URL_RE = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")
_process: subprocess.Popen | None = None


def lan_url() -> str:
    """Best-effort http URL reachable from other devices on the same wifi."""
    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # no packets sent; just picks the outbound interface
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        pass
    return f"http://{ip}:{config.PORT}"


def cloudflared_available() -> bool:
    return shutil.which("cloudflared") is not None


def public_url() -> str | None:
    return database.get_setting("tunnel_url")


def status() -> dict:
    return {
        "lan_url": lan_url(),
        "public_url": public_url(),
        "cloudflared_available": cloudflared_available(),
        "running": _process is not None and _process.poll() is None,
    }


def _reader(proc: subprocess.Popen) -> None:
    assert proc.stderr is not None
    for raw in proc.stderr:
        line = raw.decode(errors="ignore") if isinstance(raw, bytes) else raw
        match = _URL_RE.search(line)
        if match:
            url = match.group(0)
            database.set_setting("tunnel_url", url)
            event_bus.log("system", f"Secure phone link is live: {url}", level="success")
            event_bus.emit("tunnel_changed", url=url)


def start() -> None:
    """Start the quick tunnel in the background (no-op if unavailable/already running)."""
    global _process
    if _process is not None and _process.poll() is None:
        return
    if not cloudflared_available():
        event_bus.log(
            "system",
            "Phone access: cloudflared not found, using same-wifi link only. "
            f"On your phone (same wifi) open {lan_url()}.",
            level="warn")
        return
    database.set_setting("tunnel_url", "")  # clear any stale URL
    _process = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{config.PORT}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    threading.Thread(target=_reader, args=(_process,), daemon=True).start()
    event_bus.log("system", "Starting secure phone link…", level="info")


def stop() -> None:
    global _process
    if _process is not None:
        _process.terminate()
        _process = None
