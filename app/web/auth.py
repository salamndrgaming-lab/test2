"""Dashboard PIN authentication.

A single PIN/passphrase (set on first run) protects the whole dashboard, so the
secure phone link can't be used by anyone but you. The PIN is stored only as a
salted PBKDF2 hash; the raw PIN is never persisted.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from app.db import database

_PIN_KEY = "pin_hash"
_ITERATIONS = 200_000

# Paths reachable without logging in.
PUBLIC_PATHS = {"/login", "/set-pin", "/healthz"}
PUBLIC_PREFIXES = ("/static/",)


def is_pin_set() -> bool:
    return bool(database.get_setting(_PIN_KEY))


def _hash(pin: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, _ITERATIONS)


def set_pin(pin: str) -> None:
    salt = os.urandom(16)
    stored = base64.b64encode(salt).decode() + ":" + base64.b64encode(_hash(pin, salt)).decode()
    database.set_setting(_PIN_KEY, stored)


def verify_pin(pin: str) -> bool:
    stored = database.get_setting(_PIN_KEY)
    if not stored or ":" not in stored:
        return False
    salt_b64, dk_b64 = stored.split(":", 1)
    salt = base64.b64decode(salt_b64)
    expected = base64.b64decode(dk_b64)
    return hmac.compare_digest(_hash(pin, salt), expected)


def is_authed(request) -> bool:
    return bool(request.session.get("authed"))


def is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)
