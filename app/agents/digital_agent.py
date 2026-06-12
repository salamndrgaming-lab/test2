"""Digital Products agent (Milestone 2) — draft-and-handoff.

Cycle:
  1. brain writes a complete digital product (title, sections, listing copy, price)
  2. it's rendered into a REAL downloadable PDF (reportlab) + a cover image (Pollinations)
  3. an APPROVAL card is created with a download link and a one-click handoff to
     Gumroad's new-product page (their API can't create products, so you paste it)
  4. on approval the product is marked live so the bookkeeper can match real sales

Nothing is auto-published; you stay in control of what goes on sale.
"""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents.pod_agent import _parse_json
from app.brain import router as brain
from app.db import database
from app.integrations import documents, etsy, gumroad, images
from app.orchestrator import approval, event_bus

_SYSTEM = (
    "You are a digital-product creator. Respond with ONLY a JSON object, no prose, no "
    "markdown fences. Keys: product_type (ebook|guide|checklist|template), title (<70 chars), "
    "subtitle (string), niche (string), listing_description (2-3 sentence sales copy), "
    "price_usd (integer 5-29), tags (array of 5-8 short strings), cover_prompt (image prompt "
    "for a clean, professional product cover), sections (array of 6-9 objects each with "
    "'heading' and 'body'; body is 2-4 full paragraphs of genuinely useful, specific content)."
)


class DigitalAgent(BaseAgent):
    name = "digital"
    interval_minutes = 360  # propose a new product every few hours when enabled

    def register_handlers(self) -> None:
        approval.register_handler("digital_publish", self._publish_handler)

    async def run(self, *, forced: bool = False) -> None:
        if not brain.any_brain_available():
            self.log("No AI brain connected — add a Gemini or Groq key in Settings.", level="warn")
            return

        self.log("Writing a new digital product…")
        reply = await brain.generate(
            "Create one genuinely useful, sellable digital product for a specific niche audience. "
            "Make the section bodies substantive and practical, not filler." + self.avoid_repeats(),
            system=self.mission_system(_SYSTEM), task="reasoning")
        p = _parse_json(reply)
        title = p["title"].strip()[:70]
        self.remember(title, meta={"niche": p.get("niche")})
        subtitle = (p.get("subtitle") or "").strip()
        price = int(p.get("price_usd", 9))
        sections = p.get("sections", [])
        if not sections:
            self.log("Brain returned no content sections — skipping this cycle.", level="warn")
            return

        self.log(f"Building the PDF: {title} ({len(sections)} sections)…")
        _, file_url = documents.generate_pdf(title, subtitle, sections)

        cover_url = None
        try:
            self.log("Generating a cover image…")
            _, cover_url = await images.generate(
                p.get("cover_prompt", f"professional ebook cover for '{title}'"),
                width=768, height=1024, text=title, transparent=False)
        except Exception as exc:
            self.log(f"Cover image skipped ({exc}). Product still ready.", level="warn")

        db_product_id = database.execute(
            "INSERT INTO products (stream, platform, external_id, title, status, meta_json) "
            "VALUES ('digital','gumroad',NULL,?,'pending_approval',?)",
            (title, json.dumps({"file": file_url, "cover": cover_url, "price_usd": price,
                                "tags": p.get("tags", []), "type": p.get("product_type")})))

        etsy_tags = etsy.listing_tags(p.get("tags"))
        listing = (
            f"{p.get('listing_description', '').strip()}\n\n"
            f"Type: {p.get('product_type')} · Suggested price: ${price} · "
            f"Tags: {', '.join(p.get('tags', []))}\n\n"
            f"Etsy tags ({len(etsy_tags)}): {', '.join(etsy_tags)}\n\n"
            "Approve to keep it: download the file below and create the listing on Gumroad "
            "OR Etsy with this title/description/price. Reject to discard it."
        )
        approval.create(
            self.name, "digital_publish",
            title=f"Review digital product: {title}",
            summary=listing,
            payload={"db_product_id": db_product_id, "title": title, "price_usd": price,
                     "file_url": file_url, "platform": "Gumroad",
                     "handoff_url": gumroad.NEW_PRODUCT_URL,
                     "extra_handoffs": [{"platform": "Etsy", "url": etsy.ADD_LISTING_URL}]},
            preview_url=cover_url)
        self.set_status("waiting_approval")

    async def _publish_handler(self, approval_row: dict) -> None:
        d = approval_row["payload"]
        database.execute("UPDATE products SET status='live' WHERE id=?", (d["db_product_id"],))
        self.log(f"'{d['title']}' marked live. List it on Gumroad with the file & copy provided.",
                 level="success")
        self.record_win(f"Published digital product '{d['title']}'")
        self.set_status("idle")
        event_bus.emit("products_changed")
