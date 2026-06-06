"""Gumroad integration.

Important reality (verified): Gumroad's create-product API returns 404 — products
must be created in their dashboard. So we DON'T auto-create; instead the digital
agent prepares everything and hands off a one-click link to the new-product page.
The API IS used to read REAL sales for the bookkeeper.
"""
from __future__ import annotations

import httpx

from app.vault import vault

_BASE = "https://api.gumroad.com/v2"
NEW_PRODUCT_URL = "https://app.gumroad.com/products/new"


class GumroadError(Exception):
    pass


def connected() -> bool:
    return vault.has_secret("gumroad_access_token")


async def list_sales() -> list[dict]:
    """Return real sales from the connected Gumroad account (empty if not connected)."""
    token = vault.get_secret("gumroad_access_token")
    if not token:
        return []
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(f"{_BASE}/sales", params={"access_token": token})
    if resp.status_code >= 400:
        raise GumroadError(f"Gumroad sales {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return data.get("sales", []) if isinstance(data, dict) else []
