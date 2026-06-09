"""Etsy handoff (no OAuth, no API).

Etsy's listing-creation API requires an approved OAuth app plus a registered seller
account, which doesn't fit a zero-setup, human-in-the-loop tool. So — exactly like
Gumroad — we DON'T call the API. The digital agent prepares the file, listing copy
and tags, then hands off a one-click link to Etsy's "add a listing" page where you
paste them. Etsy also has no easy read API for sales here, so Etsy earnings are
recorded through the honest manual-revenue feature (copied from your payout page).
"""
from __future__ import annotations

ADD_LISTING_URL = "https://www.etsy.com/your/shops/me/tools/listings/create"
MAX_TAGS = 13  # Etsy allows up to 13 tags, each <= 20 chars


def listing_tags(tags: list[str] | None) -> list[str]:
    """Clamp tags to Etsy's limits (<=13 tags, <=20 chars each)."""
    return [str(t)[:20] for t in (tags or [])[:MAX_TAGS]]
