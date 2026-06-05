"""Local free-tier quota tracking so agents self-throttle and never get banned."""
from __future__ import annotations

from datetime import date

from app import config
from app.db import database


def _today() -> str:
    return date.today().isoformat()


def used(service: str) -> int:
    row = database.query_one(
        "SELECT units_used FROM quota_usage WHERE service=? AND day=?",
        (service, _today()),
    )
    return row["units_used"] if row else 0


def limit(service: str) -> int:
    return config.QUOTA_LIMITS.get(service, 0)


def remaining(service: str) -> int:
    lim = limit(service)
    return max(lim - used(service), 0) if lim else 10**9


def can_spend(service: str, units: int = 1) -> bool:
    lim = limit(service)
    if not lim:
        return True
    return used(service) + units <= lim


def spend(service: str, units: int = 1) -> None:
    database.execute(
        "INSERT INTO quota_usage (service, day, units_used) VALUES (?,?,?) "
        "ON CONFLICT(service, day) DO UPDATE SET units_used = units_used + excluded.units_used",
        (service, _today(), units),
    )


def snapshot() -> list[dict]:
    """Per-service usage for the dashboard."""
    out = []
    for service, lim in config.QUOTA_LIMITS.items():
        u = used(service)
        out.append({
            "service": service,
            "used": u,
            "limit": lim,
            "remaining": max(lim - u, 0),
            "pct": round(100 * u / lim, 1) if lim else 0,
        })
    return out
