"""Newsletter agent (M7) — promote to your owned email audience.

Drafts a broadcast promoting your live products and asks for approval. On approval it
EXPORTS the draft plus a recipient list (CSV) into your data folder so you can paste it
into your own free email tool and send. Nothing is ever auto-sent — no paid email
service, no API keys, you stay in control of every send.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.agents.base import BaseAgent
from app.agents.pod_agent import _parse_json
from app.brain import router as brain
from app.db import database
from app.orchestrator import approval, event_bus

_SYSTEM = (
    "You are an email marketer writing to an opt-in audience. Respond with ONLY a JSON object, "
    "no prose, no markdown fences. Keys: subject (compelling email subject line, <70 chars), "
    "body (a friendly 120-200 word email promoting the products, value-first, with a clear "
    "call to action; plain text)."
)


class NewsletterAgent(BaseAgent):
    name = "newsletter"
    interval_minutes = 10080  # weekly when enabled

    def register_handlers(self) -> None:
        approval.register_handler("newsletter_send", self._send_handler)

    async def run(self, *, forced: bool = False) -> None:
        if not brain.any_brain_available():
            self.log("No AI brain connected — add a Gemini or Groq key in Settings.", level="warn")
            return

        subs = database.query_one("SELECT COUNT(*) AS n FROM email_subscribers")["n"]
        if not subs:
            self.log("No email subscribers yet — share your blog to grow the list first.",
                     level="info")
            return

        live = database.query("SELECT title, stream FROM products WHERE status='live' LIMIT 8")
        if not live:
            self.log("No live products to feature yet — approve a product first.", level="info")
            return

        product_lines = "\n".join(f"- {p['title']} ({p['stream']})" for p in live)
        data = _parse_json(await brain.generate(
            f"Write a newsletter promoting these products:\n{product_lines}",
            system=self.mission_system(_SYSTEM), task="bulk"))
        subject = (data.get("subject") or "News from us").strip()
        body = (data.get("body") or "").strip()
        if not body:
            self.log("Brain returned no email body — skipping this cycle.", level="warn")
            return

        approval.create(
            self.name, "newsletter_send",
            title=f"Send newsletter to {subs} subscriber(s): {subject}",
            summary=(f"Subject: {subject}\n\n{body}\n\n"
                     f"Approve to EXPORT this draft + your {subs}-person recipient list to your "
                     "data folder, ready to paste into your own email tool and send. Nothing is "
                     "sent automatically."),
            payload={"subject": subject, "body": body, "recipients": subs})
        self.set_status("waiting_approval")

    async def _send_handler(self, approval_row: dict) -> None:
        d = approval_row["payload"]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = config.DATA_DIR / "newsletters" / stamp
        out.mkdir(parents=True, exist_ok=True)
        (out / "broadcast.txt").write_text(
            f"Subject: {d['subject']}\n\n{d['body']}\n", encoding="utf-8")
        rows = database.query("SELECT email, created_at FROM email_subscribers ORDER BY id")
        with (out / "recipients.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["email", "subscribed_at"])
            for r in rows:
                w.writerow([r["email"], r["created_at"]])
        self.log(f"Newsletter exported to {out} — open it, then paste into your email tool to "
                 f"send to {len(rows)} subscriber(s).", level="success",
                 payload={"folder": str(out)})
        self.set_status("idle")
        event_bus.emit("products_changed")
