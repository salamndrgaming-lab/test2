"""Marketing agent (Milestone 4) — draft-and-handoff.

Cycle:
  1. pick one of your LIVE products
  2. brain writes a platform-tailored promo post (copy + hashtags + image prompt)
  3. an optional promo graphic is generated (Pollinations)
  4. an APPROVAL card shows the post, an attachable image, and a one-click link
     that opens the platform's composer with the text PREFILLED — nothing is
     ever posted automatically; you click "Post" yourself

No social API keys or OAuth required: we use public prefilled composer URLs.
"""
from __future__ import annotations

import json
import random

from app.agents.base import BaseAgent
from app.agents.pod_agent import _parse_json
from app.brain import router as brain
from app.db import database
from app.integrations import images, social
from app.orchestrator import approval, event_bus
from app.remote import tunnel

_SYSTEM = (
    "You are a social-media marketer. Respond with ONLY a JSON object, no prose, no markdown "
    "fences. Keys: platform (one of: x, reddit, facebook, pinterest, threads, bluesky, tumblr — "
    "pick the best fit; pinterest is great for visual products), post_text (the ready-to-publish "
    "post; punchy, value-first, not spammy; <=400 chars; for X keep it tweet length), hashtags "
    "(array of 2-5 strings each starting with #), image_prompt (a prompt for an eye-catching "
    "promo graphic), subreddit (a relevant subreddit name without 'r/', or empty if platform "
    "isn't reddit)."
)


class MarketingAgent(BaseAgent):
    name = "marketing"
    interval_minutes = 180  # draft a promo every few hours when enabled

    def register_handlers(self) -> None:
        approval.register_handler("marketing_post", self._publish_handler)

    async def run(self, *, forced: bool = False) -> None:
        if not brain.any_brain_available():
            self.log("No AI brain connected — add a Gemini or Groq key in Settings.", level="warn")
            return

        live = database.query(
            "SELECT id, stream, title, meta_json FROM products WHERE status='live'")
        if not live:
            self.log("No live products to promote yet — approve a product first.", level="info")
            return

        product = random.choice(live)
        title = product["title"]
        self.log(f"Drafting a promo post for: {title}")

        reply = await brain.generate(
            f"Write one promotional social post for this product.\n"
            f"Product: {title}\nType: {product['stream']}",
            system=_SYSTEM, task="reasoning")
        p = _parse_json(reply)
        post_text = (p.get("post_text") or "").strip()
        if not post_text:
            self.log("Brain returned no post text — skipping this cycle.", level="warn")
            return
        hashtags = p.get("hashtags", [])

        image_url = None
        try:
            self.log("Generating a promo graphic…")
            _, image_url = await images.generate(
                p.get("image_prompt", f"eye-catching promo graphic for '{title}'"),
                width=1024, height=1024)
        except Exception as exc:
            self.log(f"Promo graphic skipped ({exc}). Post still ready.", level="warn")

        # Pinterest (and similar) need a PUBLIC image + destination. When the secure
        # phone link is live, the /generated image and public /blog are reachable, so
        # we can offer image-based pins; otherwise build_share_url falls back to X.
        public = tunnel.public_url()
        media = (public + image_url) if (public and image_url) else None
        link = (public + "/blog") if public else None
        label, handoff_url = social.build_share_url(
            p.get("platform", "x"), text=post_text, hashtags=hashtags, title=title,
            link=link, media=media)

        summary = (
            f"{post_text}\n\n{' '.join(hashtags)}\n\n"
            f"Promoting: {title}\n"
            f"Approve to publish on {label}: the link opens the post prefilled — review it, "
            "attach the image if you like, then hit Post. Reject to discard."
        )
        payload = {"product_id": product["id"], "title": title, "platform": label,
                   "handoff_url": handoff_url, "post_text": post_text}
        if image_url:
            payload["file_url"] = image_url
        approval.create(self.name, "marketing_post",
                        title=f"Review {label} post: {title}",
                        summary=summary, payload=payload, preview_url=image_url)
        self.set_status("waiting_approval")

    async def _publish_handler(self, approval_row: dict) -> None:
        d = approval_row["payload"]
        self.log(f"Promo for '{d['title']}' approved — open the link to publish on "
                 f"{d['platform']}.", level="success")
        # Record the approved promo on the product so we can see what's been marketed.
        row = database.query_one("SELECT meta_json FROM products WHERE id=?", (d["product_id"],))
        if row:
            meta = json.loads(row["meta_json"] or "{}")
            meta["promotions"] = meta.get("promotions", 0) + 1
            database.execute("UPDATE products SET meta_json=? WHERE id=?",
                             (json.dumps(meta), d["product_id"]))
        self.set_status("idle")
        event_bus.emit("products_changed")
