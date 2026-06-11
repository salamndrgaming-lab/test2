"""Faceless Video agent (Milestone 3) — draft-and-handoff.

Cycle:
  1. brain writes a short video: title, description, tags, narration script, and
     a handful of scene prompts + on-screen captions
  2. narration is voiced locally with Piper TTS (free, offline); if the voice
     isn't available it falls back to a silent track so the video still builds
  3. scene images are generated (Pollinations) and ffmpeg assembles a vertical
     1080x1920 MP4 with captions burned in
  4. an APPROVAL card hands you the finished MP4 to download + a one-click link
     to upload it to YouTube yourself (see integrations/youtube.py for why)
"""
from __future__ import annotations

import json

from app.agents.base import BaseAgent
from app.agents.pod_agent import _parse_json
from app.brain import router as brain
from app.db import database
from app.integrations import images, tts, video, youtube
from app.orchestrator import approval, event_bus

_SYSTEM = (
    "You are a faceless-video scriptwriter for YouTube Shorts. Respond with ONLY a JSON "
    "object, no prose, no markdown fences. Keys: topic (string), title (<70 chars, "
    "curiosity-driving), description (2-4 sentences with a call to action), tags (array of "
    "5-8 strings), hashtags (array of 3-5 strings each starting with #), narration (a single "
    "spoken script of 80-150 words, conversational, no scene labels), scenes (array of 5-7 "
    "objects each with 'image_prompt' for a striking vertical visual and 'caption', a short "
    "on-screen phrase of <=8 words). The captions together should track the narration."
)


class VideoAgent(BaseAgent):
    name = "video"
    interval_minutes = 720  # one short every ~12h when enabled

    def register_handlers(self) -> None:
        approval.register_handler("video_publish", self._publish_handler)

    async def run(self, *, forced: bool = False) -> None:
        if not brain.any_brain_available():
            self.log("No AI brain connected — add a Gemini or Groq key in Settings.", level="warn")
            return

        self.log("Writing a short video script…")
        reply = await brain.generate(
            "Create one engaging, genuinely informative faceless Short for a niche audience."
            + self.avoid_repeats(),
            system=_SYSTEM, task="reasoning")
        p = _parse_json(reply)
        title = p["title"].strip()[:70]
        self.remember(title, meta={"topic": p.get("topic")})
        narration = (p.get("narration") or "").strip()
        scene_specs = p.get("scenes", [])
        if not narration or not scene_specs:
            self.log("Brain returned no narration/scenes — skipping this cycle.", level="warn")
            return

        # --- narration (local TTS, with a silent fallback) ------------------
        try:
            self.log("Voicing the narration with Piper (local TTS)…")
            audio_path, dur = tts.synthesize(narration)
            self.log(f"Narration ready ({dur:.0f}s).")
        except tts.TTSUnavailable as exc:
            est = max(8.0, len(narration.split()) / 2.5)
            self.log(f"Narration voice unavailable ({exc}). Using a silent track "
                     "with on-screen captions instead.", level="warn")
            audio_path, _ = video.silent_wav(est)

        # --- scene images ---------------------------------------------------
        self.log(f"Generating {len(scene_specs)} scene images…")
        scenes = []
        for i, spec in enumerate(scene_specs):
            try:
                img_path, _ = await images.generate(
                    spec.get("image_prompt", title), width=720, height=1280)
                scenes.append({"image": img_path, "caption": spec.get("caption", "")})
            except Exception as exc:
                self.log(f"Scene {i+1} image failed ({exc}) — skipping it.", level="warn")
        if not scenes:
            self.log("No scene images could be generated — aborting this cycle.", level="warn")
            return

        # --- assemble -------------------------------------------------------
        self.log("Assembling the video with ffmpeg…")
        _, file_url = video.assemble(scenes, audio_path)
        thumb_url = f"/generated/{scenes[0]['image'].name}"

        db_product_id = database.execute(
            "INSERT INTO products (stream, platform, external_id, title, status, meta_json) "
            "VALUES ('video','youtube',NULL,?,'pending_approval',?)",
            (title, json.dumps({"file": file_url, "tags": p.get("tags", []),
                                "hashtags": p.get("hashtags", []),
                                "description": p.get("description", "")})))

        summary = (
            f"{p.get('description', '').strip()}\n\n"
            f"{' '.join(p.get('hashtags', []))}\n"
            f"Tags: {', '.join(p.get('tags', []))}\n\n"
            f"{youtube.QUOTA_WARNING}\n"
            "Approve to keep it (download below, then upload to YouTube). Reject to discard."
        )
        approval.create(
            self.name, "video_publish",
            title=f"Review video: {title}",
            summary=summary,
            payload={"db_product_id": db_product_id, "title": title,
                     "file_url": file_url, "platform": "YouTube",
                     "handoff_url": youtube.UPLOAD_URL},
            preview_url=thumb_url)
        self.set_status("waiting_approval")

    async def _publish_handler(self, approval_row: dict) -> None:
        d = approval_row["payload"]
        database.execute("UPDATE products SET status='live' WHERE id=?", (d["db_product_id"],))
        self.log(f"'{d['title']}' marked live. Download it and upload to YouTube.",
                 level="success")
        self.set_status("idle")
        event_bus.emit("products_changed")
