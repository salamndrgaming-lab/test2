"""Optimizer / Analyst agent — turns REAL results into the next move.

Once real sales exist, this reads what's actually selling (by product, stream and
niche), writes a plain-language "what's working" report, and stores a winner-biased
demand brief that the research step then leans on — so the team makes more of what
sells and less of what doesn't. That feedback loop is the flywheel.

It never invents revenue: with no sales it honestly reports "no winners yet". It is
read-only and needs no approval because it publishes/posts/spends nothing.
"""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents.pod_agent import _parse_json
from app.brain import router as brain
from app.db import database
from app.services import revenue

_BRIEF_SYSTEM = (
    "You are a growth analyst. Given which products and niches actually sold, propose "
    "the single best niche/direction to make MORE of next. Respond with ONLY a JSON "
    "object, no prose, no markdown fences. Keys: niche (string), audience (string), "
    "product_angle (string), keywords (array of 6-10 short SEO phrases)."
)


class OptimizerAgent(BaseAgent):
    name = "optimizer"
    interval_minutes = 1440  # once a day

    async def run(self, *, forced: bool = False) -> None:
        if not revenue.totals()["orders"]:
            self._save_report(
                "No winners yet — keep creating",
                "No real sales have come in yet, so there's nothing to optimize. The team "
                "will keep proposing varied products across niches; the moment sales appear "
                "I'll spot the winners and steer toward more of them.", {"orders": 0})
            self.log("No sales yet — nothing to optimize. Keeping variety high.", level="info")
            return

        winners = database.query(
            "SELECT p.id, p.title, p.stream, p.meta_json, "
            "       COUNT(s.id) AS orders, ROUND(SUM(s.net_amount),2) AS net "
            "FROM sales s JOIN products p ON p.id = s.product_id "
            "GROUP BY p.id ORDER BY net DESC LIMIT 5")
        by_stream = revenue.by_stream()

        niches: list[str] = []
        for w in winners:
            try:
                n = json.loads(w.get("meta_json") or "{}").get("niche")
                if n:
                    niches.append(n)
            except Exception:
                continue

        top_lines = [f"{w['title']} ({w['stream']}): {w['orders']} sales, ${w['net']}"
                     for w in winners]
        stream_lines = [f"{s['stream']}: ${s['net']} from {s['orders']} sales" for s in by_stream]
        body = ("Best-selling products:\n- " + "\n- ".join(top_lines) +
                "\n\nBy stream:\n- " + "\n- ".join(stream_lines))
        self._save_report("What's working", body, {"winners": winners, "by_stream": by_stream})
        self.log("Updated the 'what's working' report from real sales.", level="success")

        # Store a winner-biased brief for the research step to lean on next time.
        if brain.any_brain_available():
            prompt = ("These products sold best:\n- " + "\n- ".join(top_lines) +
                      (f"\n\nWinning niches: {', '.join(niches)}." if niches else ""))
            try:
                brief = _parse_json(await brain.generate(prompt, system=_BRIEF_SYSTEM, task="bulk"))
                database.execute(
                    "INSERT INTO demand_briefs (source, niche, audience, product_angle, "
                    "keywords_json) VALUES ('optimizer',?,?,?,?)",
                    (str(brief.get("niche", ""))[:200], str(brief.get("audience", ""))[:300],
                     str(brief.get("product_angle", ""))[:500],
                     json.dumps(brief.get("keywords", []))))
                self.log(f"Next focus: {brief.get('niche')}", level="success",
                         payload={"keywords": brief.get("keywords")})
            except Exception as exc:
                self.log(f"Couldn't draft a focus brief: {exc}", level="warn")

    def _save_report(self, title: str, body: str, data: dict) -> None:
        database.execute(
            "INSERT INTO reports (kind, title, body, data_json) VALUES ('optimizer',?,?,?)",
            (title, body, json.dumps(data, default=str)))
