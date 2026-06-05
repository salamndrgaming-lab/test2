"""Printify REST API client (https://developers.printify.com).

The API is free; the user pays Printify's base cost per item only when something
sells (paid out of the sale). Auth is a personal token the user pastes during
onboarding. All product creation happens as a DRAFT; publishing is gated behind
the approval flow in pod_agent.
"""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

from app.vault import vault

_BASE = "https://api.printify.com/v1"


class PrintifyError(Exception):
    pass


def connected() -> bool:
    return vault.has_secret("printify_api_token")


def _headers() -> dict:
    token = vault.get_secret("printify_api_token")
    if not token:
        raise PrintifyError("Printify is not connected. Add your API token in Settings.")
    return {"Authorization": f"Bearer {token}", "User-Agent": "AI-Income-Team"}


async def _request(method: str, path: str, **kwargs) -> dict | list:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.request(method, f"{_BASE}{path}", headers=_headers(), **kwargs)
    if resp.status_code >= 400:
        raise PrintifyError(f"Printify {method} {path} -> {resp.status_code}: {resp.text[:300]}")
    return resp.json() if resp.content else {}


async def list_shops() -> list[dict]:
    return await _request("GET", "/shops.json")


async def first_shop_id() -> int:
    shops = await list_shops()
    if not shops:
        raise PrintifyError("No Printify shop found. Create one (free) at printify.com first.")
    return shops[0]["id"]


async def upload_image(file_path: Path, file_name: str | None = None) -> str:
    """Upload a local image via base64; returns the Printify upload id."""
    contents = base64.b64encode(Path(file_path).read_bytes()).decode()
    data = await _request("POST", "/uploads/images.json",
                          json={"file_name": file_name or Path(file_path).name,
                                "contents": contents})
    return data["id"]


async def find_blueprint(keyword: str = "t-shirt") -> dict:
    """Pick a real catalog blueprint whose title matches a keyword (default: a tee)."""
    blueprints = await _request("GET", "/catalog/blueprints.json")
    kw = keyword.lower()
    for bp in blueprints:
        if kw in bp.get("title", "").lower():
            return bp
    if blueprints:
        return blueprints[0]
    raise PrintifyError("Printify catalog returned no blueprints.")


async def first_print_provider(blueprint_id: int) -> int:
    providers = await _request("GET", f"/catalog/blueprints/{blueprint_id}/print_providers.json")
    if not providers:
        raise PrintifyError("No print providers for this product type.")
    return providers[0]["id"]


async def list_variants(blueprint_id: int, provider_id: int) -> list[dict]:
    data = await _request(
        "GET", f"/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/variants.json")
    return data.get("variants", [])


async def create_draft_product(shop_id: int, *, title: str, description: str,
                               blueprint_id: int, provider_id: int,
                               variant_ids: list[int], image_id: str,
                               price_cents: int) -> dict:
    """Create a DRAFT product with the design centered on the front print area."""
    variants = [{"id": vid, "price": price_cents, "is_enabled": True} for vid in variant_ids]
    print_areas = [{
        "variant_ids": variant_ids,
        "placeholders": [{
            "position": "front",
            "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}],
        }],
    }]
    body = {
        "title": title,
        "description": description,
        "blueprint_id": blueprint_id,
        "print_provider_id": provider_id,
        "variants": variants,
        "print_areas": print_areas,
    }
    return await _request("POST", f"/shops/{shop_id}/products.json", json=body)


async def publish_product(shop_id: int, product_id: str) -> None:
    """Publish a product to the connected sales channel."""
    body = {"title": True, "description": True, "images": True, "variants": True,
            "tags": True, "keyFeatures": True, "shipping_template": True}
    await _request("POST", f"/shops/{shop_id}/products/{product_id}/publish.json", json=body)


async def list_orders(shop_id: int) -> list[dict]:
    data = await _request("GET", f"/shops/{shop_id}/orders.json")
    # The orders endpoint is paginated; the rows live under "data".
    return data.get("data", []) if isinstance(data, dict) else data
