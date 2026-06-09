"""SQLite access layer.

Single shared connection guarded by a lock. The app is a local single-user tool
so contention is negligible, and this keeps the data layer dead simple and robust.
All helpers return plain dicts so templates and JSON responses can use them directly.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from app import config

_conn: sqlite3.Connection | None = None
_lock = threading.RLock()


def _connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """Create tables (idempotent) and seed the fixed agent roster."""
    global _conn
    with _lock:
        if _conn is None:
            _conn = _connect()
        schema = (Path(config.__file__).resolve().parent / "db" / "schema.sql").read_text()
        _conn.executescript(schema)
        _conn.commit()
    _seed_agents()


def _seed_agents() -> None:
    """Insert the known agents once. Existing rows (and their enabled/status) are kept."""
    roster = [
        ("onboarding", "Setup Agent",
         "Guides you through one-time signups and stores your keys securely."),
        ("pod", "Print-on-Demand Agent",
         "Designs products, builds listings on Printify, and waits for your approval to publish."),
        ("digital", "Digital Products Agent",
         "Creates ebooks/templates and prepares ready-to-paste listings for Gumroad/Etsy."),
        ("kdp", "KDP Books Agent",
         "Designs low-content books (journals/planners) and hands off to Amazon KDP."),
        ("video", "Faceless Video Agent",
         "Writes scripts, narrates, assembles shorts, and uploads privately for your review."),
        ("blog", "SEO Blog Agent",
         "Writes keyword-targeted articles to pull in free organic traffic — you approve each."),
        ("marketing", "Marketing Agent",
         "Drafts captions and posts — every public post needs your approval first."),
        ("newsletter", "Newsletter Agent",
         "Drafts email broadcasts to your subscribers; you send them from your own email tool."),
        ("optimizer", "Optimizer Agent",
         "Studies your REAL sales and steers the team toward what's actually selling."),
        ("bookkeeper", "Bookkeeper Agent",
         "Pulls REAL sales/payout data only and keeps your revenue numbers honest."),
    ]
    with _lock:
        for name, display, desc in roster:
            _conn.execute(
                "INSERT OR IGNORE INTO agents (name, display_name, description) VALUES (?,?,?)",
                (name, display, desc),
            )
        _conn.commit()


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with _lock:
        cur = _conn.execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Run a write statement; returns lastrowid."""
    with _lock:
        cur = _conn.execute(sql, tuple(params))
        _conn.commit()
        return cur.lastrowid


# --- small typed helpers used across the app -------------------------------

def get_setting(key: str, default: str | None = None) -> str | None:
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
