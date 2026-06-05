"""Bookkeeper agent: records REAL sales only.

It reads orders from connected platforms (Printify for now) and upserts them into
the `sales` table keyed by a unique external id (idempotent — re-runs never double
count). It never writes a number that didn't come from a platform API.
"""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.db import database
from app.integrations import printify
from app.orchestrator import event_bus


class BookkeeperAgent(BaseAgent):
    name = "bookkeeper"
    interval_minutes = 60  # check for new orders hourly when enabled

    async def run(self, *, forced: bool = False) -> None:
        if not printify.connected():
            self.log("No store connected yet — nothing to reconcile.", level="info")
            return

        self.log("Checking your store for real orders…")
        shop_id = await printify.first_shop_id()
        orders = await printify.list_orders(shop_id)

        new_count = 0
        for order in orders:
            external_id = f"printify:{order.get('id')}"
            existing = database.query_one(
                "SELECT id FROM sales WHERE external_id=?", (external_id,))
            if existing:
                continue

            gross = (order.get("total_price") or 0) / 100.0  # Printify amounts are in cents
            product_db_id = self._match_product(order)
            database.execute(
                "INSERT OR IGNORE INTO sales "
                "(product_id, platform, external_id, gross_amount, fees, net_amount, "
                " currency, occurred_at, source) VALUES (?,?,?,?,?,?,?,?,?)",
                (product_db_id, "printify", external_id, gross, 0.0, gross, "USD",
                 order.get("created_at"), "printify_order"))
            new_count += 1

        if new_count:
            self.log(f"Recorded {new_count} new real order(s).", level="success")
            event_bus.emit("revenue_changed")
        else:
            self.log("No new orders since last check.", level="info")

    def _match_product(self, order: dict) -> int | None:
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
