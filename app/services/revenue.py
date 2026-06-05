"""Revenue aggregation — REAL numbers only.

Every figure here comes from the `sales` table, which the bookkeeper agent fills
exclusively from real platform data. With no sales, everything is a truthful $0.
There is intentionally no demo/seed/placeholder path in this module.
"""
from __future__ import annotations

from app.db import database


def totals() -> dict:
    row = database.query_one(
        "SELECT "
        "  COALESCE(SUM(gross_amount),0) AS gross, "
        "  COALESCE(SUM(fees),0)         AS fees, "
        "  COALESCE(SUM(net_amount),0)   AS net, "
        "  COUNT(*)                      AS orders "
        "FROM sales"
    )
    return {
        "gross": round(row["gross"], 2),
        "fees": round(row["fees"], 2),
        "net": round(row["net"], 2),
        "orders": row["orders"],
    }


def by_stream() -> list[dict]:
    return database.query(
        "SELECT COALESCE(p.stream, s.platform) AS stream, "
        "       ROUND(SUM(s.net_amount),2) AS net, COUNT(*) AS orders "
        "FROM sales s LEFT JOIN products p ON p.id = s.product_id "
        "GROUP BY COALESCE(p.stream, s.platform) "
        "ORDER BY net DESC"
    )


def recent(limit: int = 20) -> list[dict]:
    return database.query(
        "SELECT s.*, p.title AS product_title FROM sales s "
        "LEFT JOIN products p ON p.id = s.product_id "
        "ORDER BY s.occurred_at DESC, s.id DESC LIMIT ?",
        (limit,),
    )


def daily(days: int = 30) -> list[dict]:
    """Net revenue per day for the chart (only days with real sales appear)."""
    return database.query(
        "SELECT substr(occurred_at,1,10) AS day, ROUND(SUM(net_amount),2) AS net "
        "FROM sales WHERE occurred_at IS NOT NULL "
        "GROUP BY day ORDER BY day DESC LIMIT ?",
        (days,),
    )
