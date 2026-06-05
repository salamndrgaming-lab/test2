"""Digital Products agent — scheduled for Milestone 2 (built after your go-ahead).

Planned flow (draft-and-handoff, because Gumroad/Payhip can't create products via
API): generate the file + listing copy + price, then create an approval card whose
"approve" opens a one-click handoff to paste into your Gumroad/Payhip dashboard.

It is disabled by default and does nothing until we build it together.
"""
from __future__ import annotations

from app.agents.base import BaseAgent


class DigitalAgent(BaseAgent):
    name = "digital"
    interval_minutes = 0

    async def run(self, *, forced: bool = False) -> None:
        self.log("Digital Products stream isn't built yet — it's Milestone 2. "
                 "Enable it after we set it up together.", level="info")
