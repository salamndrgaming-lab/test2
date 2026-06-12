"""Free demand/trend research that steers agents toward proven-demand niches.

Signals come from FREE, key-less sources only:
  - Google Trends' public daily RSS feed (parsed with the stdlib XML reader)
  - Reddit's public JSON listings
They are synthesized by the AI brain into a short "demand brief" so the agents make
what people are actually searching for instead of random ideas.

Every source is BEST-EFFORT: if it fails or returns nothing (offline, blocked, or
rate-limited) we fall back to brain-only ideation and tag the brief's source so it's
honest about where the signal came from. Nothing here spends money, publishes, or
posts anything.

Design note: we deliberately avoid the unofficial `pytrends` scraper — it is fragile,
breaks without notice, and drags in a heavy pandas dependency. The lightweight public
RSS feed gives us the same Google Trends signal with no extra dependency.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import httpx

from app.brain import router as brain
from app.db import database

_TRENDS_RSS = "https://trends.google.com/trending/rss"
# A mix of broad pulse + buyer/gift-intent subs where purchase demand shows up.
_REDDIT_SUBS = ["popular", "Entrepreneur", "smallbusiness", "GiftIdeas", "BuyItForLife"]
_UA = {"User-Agent": "Mozilla/5.0 (AI-Income-Team)"}

_BRIEF_SYSTEM = (
    "You are an elite niche strategist for a print-on-demand and digital-products business. "
    "Your job is to find NICHE GAPS: audiences that are passionate and actively buying, but "
    "served only by generic, low-effort designs — and to define the exact angle of attack "
    "that beats what exists. Treat trending signals as raw ore: extract the durable buying "
    "audience BEHIND a trend, never the trend's protected names (no brands, celebrities, "
    "lyrics, teams — IP-safe only). Prefer specific sub-niches and passion intersections "
    "(profession x hobby) over broad crowded markets. Respond with ONLY a JSON object, no "
    "prose, no markdown fences. Keys: niche (string, the specific underserved audience), "
    "audience (string, who buys and WHY they pay), product_angle (string: the gap/weakness "
    "in what's currently offered to them, and the attack angle — what we make that beats "
    "it), keywords (array of 6-10 long-tail phrases a BUYER would actually search)."
)


def _parse_json(text: str) -> dict:
    """Extract a JSON object from a model reply, tolerating code fences."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1:
        t = t[start:end + 1]
    return json.loads(t)


async def google_trends(geo: str = "US", limit: int = 15) -> list[str]:
    """Top daily trending searches from Google Trends' public RSS (best-effort)."""
    try:
        async with httpx.AsyncClient(timeout=20, headers=_UA, follow_redirects=True) as c:
            resp = await c.get(_TRENDS_RSS, params={"geo": geo})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        # Each trend is an <item><title>…</title>; the leading channel <title> is skipped.
        titles = [el.text.strip() for el in root.iter("title") if el.text and el.text.strip()]
        return titles[1:limit + 1]
    except Exception:
        return []


async def reddit_hot(subreddits: list[str] | None = None, limit: int = 8) -> list[str]:
    """Hot post titles from public subreddits (best-effort, no auth)."""
    subs = subreddits or _REDDIT_SUBS
    out: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=20, headers=_UA, follow_redirects=True) as c:
            for sub in subs:
                try:
                    r = await c.get(f"https://www.reddit.com/r/{sub}/hot.json",
                                    params={"limit": limit})
                    r.raise_for_status()
                    for child in r.json().get("data", {}).get("children", []):
                        title = child.get("data", {}).get("title")
                        if title:
                            out.append(title.strip())
                except Exception:
                    continue
    except Exception:
        return out
    return out


async def hacker_news(limit: int = 15) -> list[str]:
    """Top Hacker News story titles (keyless Firebase API, best-effort)."""
    try:
        async with httpx.AsyncClient(timeout=20, headers=_UA, follow_redirects=True) as c:
            r = await c.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            r.raise_for_status()
            ids = r.json()[:limit]
            out: list[str] = []
            for sid in ids:
                try:
                    item = await c.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
                    title = item.json().get("title")
                    if title:
                        out.append(title.strip())
                except Exception:
                    continue
            return out
    except Exception:
        return []


def latest_optimizer_hint() -> str | None:
    """Most recent optimizer brief, used to bias new research toward proven winners."""
    row = database.query_one(
        "SELECT niche, product_angle, keywords_json FROM demand_briefs "
        "WHERE source LIKE 'optimizer%' ORDER BY id DESC LIMIT 1")
    if not row:
        return None
    try:
        kws = ", ".join(json.loads(row.get("keywords_json") or "[]"))
    except Exception:
        kws = ""
    bits = [b for b in [row.get("niche"), row.get("product_angle"), kws] if b]
    return " — ".join(bits) if bits else None


async def demand_brief() -> dict | None:
    """Synthesize and persist a demand brief from free signals.

    Returns the brief dict (with an extra ``_source`` field), or None if no AI brain
    is connected. Falls back to brain-only ideation when no live signals are available.
    """
    if not brain.any_brain_available():
        return None

    signals: list[str] = []
    sources: list[str] = []
    trends = await google_trends()
    if trends:
        signals += trends
        sources.append("trends")
    reddit = await reddit_hot()
    if reddit:
        signals += reddit
        sources.append("reddit")
    hn = await hacker_news()
    if hn:
        signals += hn
        sources.append("hn")

    source = "+".join(sources) if sources else "brain_only"
    hint = latest_optimizer_hint()

    parts = []
    if signals:
        parts.append("Trending signals right now:\n- " + "\n- ".join(signals[:25]))
    else:
        parts.append("No live trend signals are available; use evergreen buyer demand.")
    if hint:
        parts.append(f"Your best-selling direction so far: {hint}. Lean toward this.")
    parts.append("Pick ONE underserved niche we can attack with printable designs and "
                 "digital guides: name the gap in what they're currently offered and the "
                 "angle that beats it.")

    from app.brain import mission
    reply = await brain.generate("\n\n".join(parts),
                                 system=mission.compose("research", _BRIEF_SYSTEM),
                                 task="bulk")
    brief = _parse_json(reply)

    database.execute(
        "INSERT INTO demand_briefs (source, niche, audience, product_angle, keywords_json) "
        "VALUES (?,?,?,?,?)",
        (source, str(brief.get("niche", ""))[:200], str(brief.get("audience", ""))[:300],
         str(brief.get("product_angle", ""))[:500], json.dumps(brief.get("keywords", []))))
    brief["_source"] = source
    return brief
