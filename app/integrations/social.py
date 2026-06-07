"""Build prefilled "share" links for social platforms.

These are public composer URLs — no API keys, no OAuth, no rate limits. Clicking
one opens the platform with the post text already filled in; the user just hits
"Post". This keeps every public post behind a human (and behind our approval gate).
"""
from __future__ import annotations

import urllib.parse

# Platforms whose composers accept a prefilled body with no API/auth.
SUPPORTED = {"x", "twitter", "reddit", "facebook"}


def build_share_url(platform: str, *, text: str, hashtags: list[str] | None = None,
                    title: str | None = None, link: str | None = None) -> tuple[str, str]:
    """Return (human_label, prefilled_url). Falls back to X for anything unknown."""
    platform = (platform or "x").strip().lower()
    tags = " ".join(hashtags or [])
    body = f"{text}\n\n{tags}".strip()

    if platform == "reddit":
        params = {"title": (title or text)[:300]}
        params["text"] = body if not link else f"{body}\n\n{link}"
        return "Reddit", "https://www.reddit.com/submit?" + urllib.parse.urlencode(params)

    if platform == "facebook" and link:
        return "Facebook", "https://www.facebook.com/sharer/sharer.php?" + \
            urllib.parse.urlencode({"u": link, "quote": body})

    # Default: X / Twitter intent (works text-only).
    params = {"text": body}
    if link:
        params["url"] = link
    return "X (Twitter)", "https://twitter.com/intent/tweet?" + urllib.parse.urlencode(params)
