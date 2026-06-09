"""Build prefilled "share" links for social platforms.

These are public composer URLs — no API keys, no OAuth, no rate limits. Clicking
one opens the platform with the post text already filled in; the user just hits
"Post". This keeps every public post behind a human (and behind our approval gate).
"""
from __future__ import annotations

import urllib.parse

# Platforms whose composers accept a prefilled body with no API/auth.
SUPPORTED = {"x", "twitter", "reddit", "facebook",
             "pinterest", "threads", "bluesky", "tumblr"}


def build_share_url(platform: str, *, text: str, hashtags: list[str] | None = None,
                    title: str | None = None, link: str | None = None,
                    media: str | None = None) -> tuple[str, str]:
    """Return (human_label, prefilled_url). Falls back to X for anything unknown.

    `media` is a public image URL — required by Pinterest (which pins an image). If a
    Pinterest pin is requested without public media, we fall back to X so the post
    still works.
    """
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

    if platform == "pinterest" and media:
        # Pinterest pins an image and links it to a destination (the blog/product).
        params = {"url": link or media, "media": media, "description": body[:480]}
        return "Pinterest", "https://www.pinterest.com/pin/create/button/?" + \
            urllib.parse.urlencode(params)

    if platform == "threads":
        txt = body + (f"\n{link}" if link else "")
        return "Threads", "https://www.threads.net/intent/post?" + \
            urllib.parse.urlencode({"text": txt[:500]})

    if platform == "bluesky":
        txt = body + (f"\n{link}" if link else "")
        return "Bluesky", "https://bsky.app/intent/compose?" + \
            urllib.parse.urlencode({"text": txt[:300]})

    if platform == "tumblr":
        params = {"canonicalUrl": link or "", "caption": body[:480]}
        if hashtags:
            params["tags"] = ",".join(h.lstrip("#") for h in hashtags)
        return "Tumblr", "https://www.tumblr.com/widgets/share/tool?" + \
            urllib.parse.urlencode(params)

    # Default: X / Twitter intent (works text-only).
    params = {"text": body}
    if link:
        params["url"] = link
    return "X (Twitter)", "https://twitter.com/intent/tweet?" + urllib.parse.urlencode(params)
