"""Faceless Video agent — scheduled for Milestone 3 (built after your go-ahead).

Planned flow: script (brain) -> narration (Piper TTS) -> images (Pollinations) ->
assemble short (ffmpeg) -> upload to YouTube as PRIVATE -> approval card with a
player -> publish public only after you've passed the YouTube compliance audit.

Disabled by default; does nothing until we build it together.
"""
from __future__ import annotations

from app.agents.base import BaseAgent


class VideoAgent(BaseAgent):
    name = "video"
    interval_minutes = 0

    async def run(self, *, forced: bool = False) -> None:
        self.log("Faceless Video stream isn't built yet — it's Milestone 3. "
                 "Enable it after we set it up together.", level="info")
