"""SEO blog agent (M7) — compounding free organic traffic.

Writes a keyword-targeted article about a niche/product as a DRAFT and asks for your
approval. Approved posts go live on the public /blog (reachable via your secure phone
link) and can be exported as static HTML for free hosting (Netlify/GitHub Pages). Each
article ends with a call-to-action pointing readers at your products. Nothing is
published without your approval.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.agents.pod_agent import _parse_json
from app.brain import router as brain
from app.db import database
from app.orchestrator import approval, event_bus

_SYSTEM = (
    "You are an SEO content writer. Write a helpful, genuine blog article (NOT spammy) for a "
    "niche audience that would buy related products. Respond with ONLY a JSON object, no prose, "
    "no markdown fences. Keys: title (<70 chars, search-friendly), summary (1-2 sentences), "
    "keywords (array of 5-10 short SEO phrases), sections (array of 3-6 objects each with "
    "heading (string) and body (a 2-4 sentence paragraph string)), cta (one sentence "
    "encouraging the reader to check out the product)."
)


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:60] or "post"


def _render_body(data: dict, product_title: str | None) -> str:
    """Server-render the model's structured content to safe, escaped HTML."""
    parts = [f"<p>{html.escape(data.get('summary', ''))}</p>"]
    for sec in data.get("sections", []):
        if sec.get("heading"):
            parts.append(f"<h2>{html.escape(str(sec['heading']))}</h2>")
        if sec.get("body"):
            parts.append(f"<p>{html.escape(str(sec['body']))}</p>")
    cta = data.get("cta")
    if cta:
        label = f" — {html.escape(product_title)}" if product_title else ""
        parts.append(f'<p class="cta"><strong>{html.escape(str(cta))}</strong>{label}</p>')
    return "\n".join(parts)


class BlogAgent(BaseAgent):
    name = "blog"
    interval_minutes = 720  # a fresh article a couple of times a day when enabled

    def register_handlers(self) -> None:
        approval.register_handler("blog_publish", self._publish_handler)

    async def run(self, *, forced: bool = False) -> None:
        if not brain.any_brain_available():
            self.log("No AI brain connected — add a Gemini or Groq key in Settings.", level="warn")
            return

        # Prefer a real live product to write around; else the latest demand-brief niche.
        product = database.query_one(
            "SELECT id, title FROM products WHERE status='live' ORDER BY id DESC LIMIT 1")
        brief = database.query_one("SELECT niche FROM demand_briefs ORDER BY id DESC LIMIT 1")
        subject = ((product["title"] if product else None)
                   or (brief["niche"] if brief else None) or "a popular niche")
        self.log(f"Writing an SEO article about: {subject}")

        data = _parse_json(await brain.generate(
            f"Write a blog article that would attract buyers interested in: {subject}."
            + self.avoid_repeats(),
            system=self.mission_system(_SYSTEM), task="bulk"))
        title = (data.get("title") or subject).strip()[:120]
        self.remember(title, meta={"subject": subject})
        product_title = product["title"] if product else None
        body_html = _render_body(data, product_title)
        slug = self._unique_slug(_slugify(title))

        post_id = database.execute(
            "INSERT INTO blog_posts (slug, title, summary, body_html, keywords_json, "
            "product_id, status) VALUES (?,?,?,?,?,?, 'draft')",
            (slug, title, data.get("summary", ""), body_html,
             json.dumps(data.get("keywords", [])), product["id"] if product else None))

        approval.create(
            self.name, "blog_publish",
            title=f"Publish blog post: {title}",
            summary=(f"{data.get('summary', '')}\n\n"
                     f"Keywords: {', '.join(data.get('keywords', []))}\n\n"
                     "Approve to publish it on your public blog (and make it exportable for free "
                     "hosting). Reject to discard."),
            payload={"post_id": post_id, "slug": slug, "title": title})
        self.set_status("waiting_approval")

    def _unique_slug(self, base: str) -> str:
        slug, i = base, 2
        while database.query_one("SELECT 1 FROM blog_posts WHERE slug=?", (slug,)):
            slug = f"{base}-{i}"
            i += 1
        return slug

    async def _publish_handler(self, approval_row: dict) -> None:
        p = approval_row["payload"]
        database.execute(
            "UPDATE blog_posts SET status='published', published_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), p["post_id"]))
        self.log(f"Blog post '{p['title']}' is live at /blog/{p['slug']}.", level="success")
        self.record_win(f"Published blog post '{p['title']}'")
        self.set_status("idle")
        event_bus.emit("products_changed")
