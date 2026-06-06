"""Bookkeeper agent: records REAL sales only.

It reads orders from connected platforms (Printify for now) and upserts them into
the `sales` table keyed by a unique external id (idempotent — re-runs never double
count). It never writes a number that didn't come from a platform API.
"""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.db import database
from app.integrations import gumroad, printify
from app.orchestrator import event_bus


class BookkeeperAgent(BaseAgent):
    name = "bookkeeper"
    interval_minutes = 60  # check for new orders hourly when enabled

    async def run(self, *, forced: bool = False) -> None:
        if not printify.connected() and not gumroad.connected():
            self.log("No store connected yet — nothing to reconcile.", level="info")
            return

        new_count = 0
        if printify.connected():
            new_count += await self._reconcile_printify()
        if gumroad.connected():
            new_count += await self._reconcile_gumroad()

        if new_count:
            self.log(f"Recorded {new_count} new real sale(s).", level="success")
            event_bus.emit("revenue_changed")
        else:
            self.log("No new sales since last check.", level="info")

    def _save_sale(self, *, product_id, platform, external_id, gross, fees,
                   currency, occurred_at, source) -> bool:
        if database.query_one("SELECT id FROM sales WHERE external_id=?", (external_id,)):
            return False
        database.execute(
            "INSERT OR IGNORE INTO sales "
            "(product_id, platform, external_id, gross_amount, fees, net_amount, "
            " currency, occurred_at, source) VALUES (?,?,?,?,?,?,?,?,?)",
            (product_id, platform, external_id, gross, fees, gross - fees,
             currency, occurred_at, source))
        return True

    async def _reconcile_printify(self) -> int:
        self.log("Checking your Printify store for real orders…")
        shop_id = await printify.first_shop_id()
        orders = await printify.list_orders(shop_id)
        count = 0
        for order in orders:
            gross = (order.get("total_price") or 0) / 100.0  # Printify amounts are in cents
            if self._save_sale(product_id=self._match_printify(order), platform="printify",
                               external_id=f"printify:{order.get('id')}", gross=gross, fees=0.0,
                               currency="USD", occurred_at=order.get("created_at"),
                               source="printify_order"):
                count += 1
        return count

    async def _reconcile_gumroad(self) -> int:
        self.log("Checking Gumroad for real sales…")
        count = 0
        for sale in await gumroad.list_sales():
            gross = (sale.get("price") or 0) / 100.0  # cents
            fees = (sale.get("gumroad_fee") or 0) / 100.0
            if self._save_sale(product_id=self._match_gumroad(sale), platform="gumroad",
                               external_id=f"gumroad:{sale.get('id')}", gross=gross, fees=fees,
                               currency=(sale.get("currency") or "usd").upper(),
                               occurred_at=sale.get("created_at"), source="gumroad_sale"):
                count += 1
        return count

    def _match_gumroad(self, sale: dict) -> int | None:
        name = sale.get("product_name")
        if not name:
            return None
        row = database.query_one(
            "SELECT id FROM products WHERE stream='digital' AND title=?", (name,))
        return row["id"] if row else None

    def _match_printify(self, order: dict) -> int | None:
        """Best-effort link an order to a product we created, via Printify product id."""
        for item in order.get("line_items", []):
            ext = item.get("product_id")
            if not ext:
                continue
            row = database.query_one(
                "SELECT id FROM products WHERE external_id=?", (str(ext),))
            if row:
                return row["id"]
        return None
