"""Print-on-Demand agent (the first real income loop).

Cycle:
  1. brain invents a niche + product concept + design prompt
  2. Pollinations generates the design image (free)
  3. Printify uploads the art and creates a DRAFT product on a real blueprint
  4. an APPROVAL is created — the agent stops and waits for you
  5. on approval, the registered handler publishes the product to your store

No sales are ever invented; the bookkeeper records real orders separately.
"""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.brain import router as brain
from app.db import database
from app.integrations import images, printify
from app.orchestrator import approval, event_bus

# Default retail price (cents) applied to all variants. You can change it in
# Printify before/after publishing; the approval card shows it plainly.
DEFAULT_PRICE_CENTS = 2499

_CONCEPT_SYSTEM = (
    "You are a print-on-demand product designer. Respond with ONLY a JSON object, "
    "no prose, no markdown fences. Keys: niche (string), product_title (string, <60 chars), "
    "description (string, 1-2 sentences for the listing), design_prompt (string, a vivid "
    "text-to-image prompt for a clean, printable t-shirt graphic on a transparent/plain "
    "background), tags (array of 5-8 short strings)."
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


class PodAgent(BaseAgent):
    name = "pod"
    interval_minutes = 180  # propose a new product every few hours when enabled

    def register_handlers(self) -> None:
        approval.register_handler("pod_publish", self._publish_handler)

    async def run(self, *, forced: bool = False) -> None:
        if not brain.any_brain_available():
            self.log("No AI brain connected — add a Gemini or Groq key in Settings.", level="warn")
            return
        if not printify.connected():
            self.log("Printify isn't connected yet — add your token in Settings.", level="warn")
            return

        self.log("Brainstorming a new product idea…")
        reply = await brain.generate(
            "Invent one fresh, marketable t-shirt product concept for a specific niche audience.",
            system=_CONCEPT_SYSTEM, task="reasoning")
        concept = _parse_json(reply)
        title = concept["product_title"].strip()[:60]
        description = concept["description"].strip()
        design_prompt = concept["design_prompt"].strip()
        self.log(f"Concept: {title}", level="success",
                 payload={"niche": concept.get("niche"), "tags": concept.get("tags")})

        self.log("Generating the design artwork…")
        img_path, web_path = await images.generate(design_prompt)

        self.log("Setting up the product on Printify…")
        shop_id = await printify.first_shop_id()
        blueprint = await printify.find_blueprint("t-shirt")
        provider_id = await printify.first_print_provider(blueprint["id"])
        variants = await printify.list_variants(blueprint["id"], provider_id)
        variant_ids = [v["id"] for v in variants]
        image_id = await printify.upload_image(img_path)

        product = await printify.create_draft_product(
            shop_id, title=title, description=description,
            blueprint_id=blueprint["id"], provider_id=provider_id,
            variant_ids=variant_ids, image_id=image_id, price_cents=DEFAULT_PRICE_CENTS)
        product_external_id = product["id"]

        db_product_id = database.execute(
            "INSERT INTO products (stream, platform, external_id, title, status, meta_json) "
            "VALUES ('pod','printify',?,?,'pending_approval',?)",
            (product_external_id, title, json.dumps({
                "design": web_path, "blueprint": blueprint.get("title"),
                "price_cents": DEFAULT_PRICE_CENTS, "tags": concept.get("tags", [])})))

        approval.create(
            self.name, "pod_publish",
            title=f"Publish product: {title}",
            summary=(f"{description}\n\nProduct type: {blueprint.get('title')} · "
                     f"Price: ${DEFAULT_PRICE_CENTS/100:.2f} · {len(variant_ids)} variants. "
                     "Approve to publish it live to your store; reject to discard."),
            payload={"shop_id": shop_id, "product_id": product_external_id,
                     "db_product_id": db_product_id, "title": title},
            preview_url=web_path)
        self.set_status("waiting_approval")

    async def _publish_handler(self, approval_row: dict) -> None:
        p = approval_row["payload"]
        self.log(f"Publishing '{p['title']}' to your store…")
        await printify.publish_product(p["shop_id"], p["product_id"])
        database.execute("UPDATE products SET status='live' WHERE id=?", (p["db_product_id"],))
        self.log(f"'{p['title']}' is now live in your store.", level="success")
        self.set_status("idle")
        event_bus.emit("products_changed")
