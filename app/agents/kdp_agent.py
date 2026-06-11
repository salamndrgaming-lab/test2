"""Amazon KDP agent (M8) — low/no-content books, draft-and-handoff.

Cycle:
  1. brain designs a low-content book (journal/planner/notebook) for a niche
  2. a real print-ready interior PDF is generated (reportlab) + a cover (Pollinations)
  3. an APPROVAL card shows the files, listing copy, and a one-click handoff to KDP's
     "create paperback" page — KDP has no create API, so you upload there yourself
  4. on approval the product is marked live; KDP royalties are logged via manual revenue

Nothing is auto-published; you upload to KDP and finish the cover in KDP Cover Creator.
"""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents.pod_agent import _parse_json
from app.brain import router as brain
from app.db import database
from app.integrations import documents, images, kdp
from app.orchestrator import approval, event_bus

_SYSTEM = (
    "You design low/no-content Amazon KDP paperbacks (journals, planners, notebooks, "
    "logbooks). Respond with ONLY a JSON object, no prose, no markdown fences. Keys: "
    "title (<70 chars), subtitle (string), niche (string), page_style (one of: lined, dot, "
    "grid, blank), pages (integer 100-160), keywords (array of 5-8 short strings), "
    "description (2-3 sentence sales copy), cover_prompt (image prompt for a clean 6x9 book "
    "cover with NO text, just artwork/pattern fitting the niche)."
)
_STYLES = {"lined", "dot", "grid", "blank"}


class KdpAgent(BaseAgent):
    name = "kdp"
    interval_minutes = 720  # propose a book a couple of times a day when enabled

    def register_handlers(self) -> None:
        approval.register_handler("kdp_publish", self._publish_handler)

    async def run(self, *, forced: bool = False) -> None:
        if not brain.any_brain_available():
            self.log("No AI brain connected — add a Gemini or Groq key in Settings.", level="warn")
            return

        self.log("Designing a low-content KDP book…")
        p = _parse_json(await brain.generate(
            "Design one low-content KDP book people in a specific niche would buy."
            + self.avoid_repeats(),
            system=_SYSTEM, task="reasoning"))
        title = (p.get("title") or "Untitled").strip()[:70]
        self.remember(title, meta={"niche": p.get("niche")})
        style = p.get("page_style") if p.get("page_style") in _STYLES else "lined"
        pages = max(100, min(int(p.get("pages", 120)), 200))

        self.log(f"Building the interior PDF: {title} ({pages} {style} pages)…")
        _, file_url = documents.generate_interior(title, page_style=style, pages=pages)

        cover_url = None
        try:
            self.log("Generating a cover image…")
            _, cover_url = await images.generate(
                p.get("cover_prompt", f"clean 6x9 book cover artwork for '{title}', no text"),
                width=1024, height=1536)
        except Exception as exc:
            self.log(f"Cover image skipped ({exc}). Book still ready.", level="warn")

        db_product_id = database.execute(
            "INSERT INTO products (stream, platform, external_id, title, status, meta_json) "
            "VALUES ('kdp','amazon_kdp',NULL,?,'pending_approval',?)",
            (title, json.dumps({"file": file_url, "cover": cover_url, "page_style": style,
                                "pages": pages, "trim": kdp.DEFAULT_TRIM,
                                "keywords": p.get("keywords", [])})))

        listing = (
            f"{p.get('description', '').strip()}\n\n"
            f"{pages} {style} pages · Trim: {kdp.DEFAULT_TRIM} · "
            f"Keywords: {', '.join(p.get('keywords', []))}\n\n"
            "Approve to keep it: download the interior PDF, then upload it on KDP and finish "
            "the cover in KDP Cover Creator. Reject to discard."
        )
        approval.create(
            self.name, "kdp_publish",
            title=f"Review KDP book: {title}",
            summary=listing,
            payload={"db_product_id": db_product_id, "title": title, "file_url": file_url,
                     "platform": "Amazon KDP", "handoff_url": kdp.CREATE_PAPERBACK_URL},
            preview_url=cover_url)
        self.set_status("waiting_approval")

    async def _publish_handler(self, approval_row: dict) -> None:
        d = approval_row["payload"]
        database.execute("UPDATE products SET status='live' WHERE id=?", (d["db_product_id"],))
        self.log(f"'{d['title']}' marked live. Upload it on KDP with the interior & copy "
                 "provided.", level="success")
        self.set_status("idle")
        event_bus.emit("products_changed")
