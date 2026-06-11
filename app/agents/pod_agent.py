"""Print-on-Demand agent (the first real income loop).

Cycle (per run):
  1. best-effort demand research picks a proven-demand niche (free trend signals)
  2. for each idea in the batch: the brain invents a concept + design prompt
  3. Pollinations generates the design image (free) — once per idea
  4. that ONE design is placed on every configured blueprint (tee, mug, sticker,
     poster…), creating several DRAFT products from a single image
  5. an APPROVAL is created per idea — the agent stops and waits for you
  6. on approval, the registered handler publishes every product in that idea live

This multiplies output: a few ideas × several blueprints = many SKUs per run, all
behind one approval each. No sales are ever invented; the bookkeeper records real
orders separately.
"""
from __future__ import annotations

import json

from app import config
from app.agents.base import BaseAgent
from app.brain import router as brain
from app.db import database
from app.integrations import images, printify, research
from app.orchestrator import approval, event_bus

# Default retail price (cents) applied to all variants. You can change it in
# Printify before/after publishing; the approval card shows it plainly.
DEFAULT_PRICE_CENTS = 2499

_CONCEPT_SYSTEM = (
    "You are a print-on-demand product designer. Respond with ONLY a JSON object, "
    "no prose, no markdown fences. Keys: niche (string), product_title (string, <60 chars), "
    "description (string, 1-2 sentences for the listing), design_prompt (string, a vivid "
    "text-to-image prompt for a clean, printable graphic on a transparent/plain background "
    "that works across products like shirts, mugs, stickers and posters), tags (array of "
    "5-8 short strings)."
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
    interval_minutes = 180  # propose new products every few hours when enabled

    def register_handlers(self) -> None:
        approval.register_handler("pod_publish", self._publish_handler)

    async def run(self, *, forced: bool = False) -> None:
        if not brain.any_brain_available():
            self.log("No AI brain connected — add a Gemini or Groq key in Settings.", level="warn")
            return
        if not printify.connected():
            self.log("Printify isn't connected yet — add your token in Settings.", level="warn")
            return

        # Best-effort demand research so we make what people are actually searching for.
        brief = None
        try:
            brief = await research.demand_brief()
            if brief:
                self.log(f"Demand brief ({brief.get('_source')}): {brief.get('niche')}",
                         level="info", payload={"keywords": brief.get("keywords")})
        except Exception as exc:
            self.log(f"Trend research unavailable ({exc}); using the brain's own ideas.",
                     level="warn")

        self.log("Loading product blueprints from Printify…")
        shop_id = await printify.first_shop_id()
        blueprint_specs = await self._resolve_blueprints()
        if not blueprint_specs:
            self.log("Couldn't load any Printify blueprints right now.", level="warn")
            return

        batch = max(1, int(config.BATCH.get("pod", 1)))
        created = 0
        for n in range(batch):
            try:
                await self._propose_one(shop_id, blueprint_specs, brief, n + 1, batch)
                created += 1
            except Exception as exc:
                self.log(f"Idea {n + 1}/{batch} failed: {exc}", level="warn")
        if created:
            self.set_status("waiting_approval")

    async def _resolve_blueprints(self) -> list[dict]:
        """Resolve each configured blueprint (type/provider/variants) once per run."""
        specs: list[dict] = []
        for kw in config.POD_BLUEPRINTS:
            try:
                bp = await printify.find_blueprint(kw)
                provider_id = await printify.first_print_provider(bp["id"])
                variants = await printify.list_variants(bp["id"], provider_id)
                variant_ids = [v["id"] for v in variants]
                if variant_ids:
                    specs.append({"keyword": kw, "blueprint": bp,
                                  "provider_id": provider_id, "variant_ids": variant_ids})
            except Exception as exc:
                self.log(f"Skipping '{kw}' blueprint: {exc}", level="warn")
        return specs

    async def _propose_one(self, shop_id: int, blueprint_specs: list[dict],
                           brief: dict | None, idx: int, total: int) -> None:
        self.log(f"Brainstorming product idea {idx}/{total}…")
        user_prompt = "Invent one fresh, marketable product concept for a specific niche audience."
        if brief:
            kws = ", ".join(brief.get("keywords", []) or [])
            user_prompt = (
                f"Invent one fresh, marketable product concept for this niche: "
                f"{brief.get('niche')} (audience: {brief.get('audience')}). "
                f"Angle: {brief.get('product_angle')}. Lean into these keywords: {kws}.")
        # Persistent memory: never re-pitch a concept we've already made.
        user_prompt += self.avoid_repeats()

        concept = _parse_json(await brain.generate(user_prompt, system=_CONCEPT_SYSTEM,
                                                   task="reasoning"))
        title = concept["product_title"].strip()[:60]
        description = concept["description"].strip()
        design_prompt = concept["design_prompt"].strip()
        niche = concept.get("niche") or (brief.get("niche") if brief else None)
        self.remember(title, meta={"niche": niche, "tags": concept.get("tags")})
        self.log(f"Concept: {title}", level="success",
                 payload={"niche": niche, "tags": concept.get("tags")})

        self.log("Generating the design artwork…")
        img_path, web_path = await images.generate(design_prompt)
        image_id = await printify.upload_image(img_path)  # upload the design ONCE

        self.log(f"Placing the design on {len(blueprint_specs)} product types…")
        items: list[dict] = []
        for spec in blueprint_specs:
            bp = spec["blueprint"]
            product = await printify.create_draft_product(
                shop_id, title=title, description=description,
                blueprint_id=bp["id"], provider_id=spec["provider_id"],
                variant_ids=spec["variant_ids"], image_id=image_id,
                price_cents=DEFAULT_PRICE_CENTS)
            db_id = database.execute(
                "INSERT INTO products (stream, platform, external_id, title, status, meta_json) "
                "VALUES ('pod','printify',?,?,'pending_approval',?)",
                (product["id"], title, json.dumps({
                    "design": web_path, "blueprint": bp.get("title"), "niche": niche,
                    "price_cents": DEFAULT_PRICE_CENTS, "tags": concept.get("tags", [])})))
            items.append({"product_id": product["id"], "db_product_id": db_id,
                          "blueprint": bp.get("title")})

        types = ", ".join(i["blueprint"] for i in items if i.get("blueprint"))
        approval.create(
            self.name, "pod_publish",
            title=f"Publish: {title} ({len(items)} products)",
            summary=(f"{description}\n\nProduct types: {types} · "
                     f"Price: ${DEFAULT_PRICE_CENTS / 100:.2f} each. "
                     "Approve to publish them all live to your store; reject to discard."),
            payload={"shop_id": shop_id, "products": items, "title": title},
            preview_url=web_path)

    async def _publish_handler(self, approval_row: dict) -> None:
        p = approval_row["payload"]
        shop_id = p["shop_id"]
        # Support the multi-product payload (and any legacy single-product one).
        items = p.get("products") or [{"product_id": p.get("product_id"),
                                       "db_product_id": p.get("db_product_id")}]
        self.log(f"Publishing '{p.get('title')}' ({len(items)} products) to your store…")
        published = 0
        for item in items:
            if not item.get("product_id"):
                continue
            await printify.publish_product(shop_id, item["product_id"])
            if item.get("db_product_id"):
                database.execute("UPDATE products SET status='live' WHERE id=?",
                                 (item["db_product_id"],))
            published += 1
        self.log(f"'{p.get('title')}' is now live ({published} products).", level="success")
        self.set_status("idle")
        event_bus.emit("products_changed")
