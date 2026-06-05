"""Marketing agent — scheduled for Milestone 4 (built after your go-ahead).

Planned flow: draft captions/posts for your products; every public post is gated
behind an approval card before anything is posted to a social account.

Disabled by default; does nothing until we build it together.
"""
from __future__ import annotations

from app.agents.base import BaseAgent


class MarketingAgent(BaseAgent):
    name = "marketing"
    interval_minutes = 0

    async def run(self, *, forced: bool = False) -> None:
        self.log("Marketing stream isn't built yet — it's Milestone 4. "
                 "Enable it after we set it up together.", level="info")
