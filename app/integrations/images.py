"""Free image generation via Pollinations.ai (no API key required).

Saves PNGs into data/generated/ and returns (absolute_path, web_path) where
web_path is what the dashboard uses to preview the image.
"""
from __future__ import annotations

import time
import urllib.parse
from pathlib import Path

import httpx

from app import config

_BASE = "https://image.pollinations.ai/prompt/"


async def generate(prompt: str, *, width: int = 1024, height: int = 1024,
                   model: str = "flux", filename: str | None = None) -> tuple[Path, str]:
    config.ensure_dirs()
    encoded = urllib.parse.quote(prompt)
    # `referrer` identifies the app to Pollinations (recommended for the free tier);
    # a browser-style UA avoids occasional bot blocks.
    params = {"width": width, "height": height, "model": model, "nologo": "true",
              "seed": int(time.time()), "referrer": "ai-income-team"}
    headers = {"User-Agent": "Mozilla/5.0 (AI-Income-Team)"}

    async with httpx.AsyncClient(timeout=180, follow_redirects=True, headers=headers) as client:
        resp = await client.get(_BASE + encoded, params=params)
    resp.raise_for_status()

    name = filename or f"design_{int(time.time()*1000)}.png"
    out_path = config.GENERATED_DIR / name
    out_path.write_bytes(resp.content)
    return out_path, f"/generated/{name}"
