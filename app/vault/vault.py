"""Secure, local-only API-key vault.

Secrets are encrypted at rest with Fernet (AES). The encryption key itself is
stored in the OS keyring (Windows Credential Manager / macOS Keychain) when
available — the secure default. If no keyring backend exists (e.g. a headless
machine), it falls back to a local key file with locked-down permissions.

Secret VALUES never touch SQLite or the activity log. The DB only records which
services are connected (`secrets_meta`).
"""
from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone

from cryptography.fernet import Fernet

from app import config
from app.db import database

_KEYRING_KEY = "vault_master_key"


def _load_or_create_fernet_key() -> bytes:
    """Get the Fernet key from the OS keyring, or fall back to a local key file."""
    # Preferred: OS keyring.
    try:
        import keyring  # imported lazily so a missing backend can't break startup
        existing = keyring.get_password(config.KEYRING_SERVICE, _KEYRING_KEY)
        if existing:
            return existing.encode()
        key = Fernet.generate_key()
        keyring.set_password(config.KEYRING_SERVICE, _KEYRING_KEY, key.decode())
        return key
    except Exception:
        pass  # no usable keyring backend — use the file fallback below

    # Fallback: local key file (chmod 600). Less ideal than the OS keyring but
    # still keeps the vault encrypted at rest on this machine.
    config.ensure_dirs()
    if config.VAULT_KEY_FILE.exists():
        return config.VAULT_KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    config.VAULT_KEY_FILE.write_bytes(key)
    try:
        os.chmod(config.VAULT_KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # e.g. Windows — best effort
    return key


def _fernet() -> Fernet:
    return Fernet(_load_or_create_fernet_key())


def _read_all() -> dict[str, str]:
    if not config.VAULT_FILE.exists():
        return {}
    try:
        raw = _fernet().decrypt(config.VAULT_FILE.read_bytes())
        return json.loads(raw.decode())
    except Exception:
        # Corrupt or unreadable vault: treat as empty rather than crashing.
        return {}


def _write_all(data: dict[str, str]) -> None:
    config.ensure_dirs()
    token = _fernet().encrypt(json.dumps(data).encode())
    config.VAULT_FILE.write_bytes(token)
    try:
        os.chmod(config.VAULT_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def get_secret(name: str) -> str | None:
    return _read_all().get(name)


def set_secret(name: str, value: str) -> None:
    data = _read_all()
    data[name] = value
    _write_all(data)
    _mark_connected(name, True)


def delete_secret(name: str) -> None:
    data = _read_all()
    if name in data:
        del data[name]
        _write_all(data)
    _mark_connected(name, False)


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def _mark_connected(name: str, connected: bool) -> None:
    now = datetime.now(timezone.utc).isoformat() if connected else None
    database.execute(
        "INSERT INTO secrets_meta (service, is_connected, connected_at) VALUES (?,?,?) "
        "ON CONFLICT(service) DO UPDATE SET is_connected=excluded.is_connected, "
        "connected_at=excluded.connected_at",
        (name, 1 if connected else 0, now),
    )


def connection_status() -> dict[str, bool]:
    """Return {secret_name: is_connected} for every known secret slot."""
    present = set(_read_all().keys())
    return {name: (name in present) for name in config.SECRET_KEYS}
