"""Image generation with automatic provider fallback.

Pollinations.ai used to allow anonymous use, but it now gates generation behind a
registered token. We support two FREE token providers, then a keyless local
designer so the pipeline never stalls. Order:

  1. Pollinations (token, no-watermark)  — free token from https://auth.pollinations.ai
  2. Hugging Face (token)                — free token from https://huggingface.co/settings/tokens
  3. Pollinations (token, watermarked)   — some free tiers reject `nologo`; try without
  4. Pollinations (anonymous)            — last-ditch, in case a tier still allows it
  5. Local keyless design                — offline Pillow typographic render (always works)

Each failed online attempt is logged to the activity feed with the exact reason
(HTTP status / content-type), so a persistent fall-through to the local design is
diagnosable instead of silent. See app/integrations/local_art.py.

Saves PNGs into data/generated/ and returns (absolute_path, web_path).
"""
from __future__ import annotations

import time
import urllib.parse
from pathlib import Path

import httpx

from app import config
from app.integrations import local_art
from app.orchestrator import event_bus
from app.vault import vault

_POLLI = "https://image.pollinations.ai/prompt/"
# HF moved off api-inference.huggingface.co to the Inference Providers router.
_HF = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"


def _is_image(resp) -> bool:
    return resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image")


def _describe(resp) -> str:
    body = ""
    if not _is_image(resp):
        # Surface a short slice of the error body (JSON/text) — that's what tells us
        # *why* (e.g. Pollinations "payment required", HF "model loading").
        try:
            body = " " + resp.text[:160].replace("\n", " ").strip()
        except Exception:
            body = ""
    return f"HTTP {resp.status_code} ({resp.headers.get('content-type', 'no content-type')}){body}"


def _log(message: str, level: str = "warn") -> None:
    try:
        event_bus.log("images", message, level=level)
    except Exception:
        pass


async def _try_pollinations(client, prompt, width, height, model, token, nologo):
    params = {"width": width, "height": height, "seed": int(time.time()),
              "referrer": "ai-income-team", "model": model}
    headers = {"User-Agent": "Mozilla/5.0 (AI-Income-Team)"}
    if token:
        params["token"] = token
        headers["Authorization"] = f"Bearer {token}"
    if nologo:
        params["nologo"] = "true"
    resp = await client.get(_POLLI + urllib.parse.quote(prompt), params=params, headers=headers)
    return resp.content if _is_image(resp) else None, _describe(resp)


async def _try_huggingface(client, prompt, width, height, token):
    if not token:
        return None, "no Hugging Face token"
    resp = await client.post(
        _HF,
        headers={"Authorization": f"Bearer {token}", "Accept": "image/png",
                 "x-wait-for-model": "true"},  # wait if the model is cold instead of 503
        json={"inputs": prompt})
    return resp.content if _is_image(resp) else None, _describe(resp)


def _phrase_from_prompt(prompt: str) -> str:
    """Derive a short, human phrase from an image prompt for the keyless fallback,
    dropping art-direction filler so the rendered text reads like a real design."""
    filler = {"a", "an", "the", "of", "for", "with", "and", "on", "in", "minimalist",
              "vector", "graphic", "design", "illustration", "clean", "modern", "art",
              "artwork", "background", "transparent", "plain", "style", "high", "quality"}
    words = [w for w in prompt.replace(",", " ").split() if w.lower() not in filler]
    return " ".join(words[:6]) or prompt[:40]


def _save(content: bytes, filename: str | None) -> tuple[Path, str]:
    name = filename or f"design_{int(time.time()*1000)}.png"
    out_path = config.GENERATED_DIR / name
    out_path.write_bytes(content)
    return out_path, f"/generated/{name}"


async def generate(prompt: str, *, width: int = 1024, height: int = 1024,
                   model: str = "flux", filename: str | None = None,
                   text: str | None = None, transparent: bool = True) -> tuple[Path, str]:
    """Generate an image, trying online providers then a keyless local design.

    `text` is the phrase to render if we fall back to the local generator (e.g. the
    product title); when omitted it's derived from `prompt`. `transparent` controls
    the local fallback only (True = text-on-transparent for merch, False = gradient
    background for video scenes). This never raises for lack of a token.
    """
    config.ensure_dirs()
    polli_token = vault.get_secret("pollinations_token")
    hf_token = vault.get_secret("huggingface_token")

    # (label, factory) in priority order. Clean token providers first, then a
    # watermarked Pollinations retry (some free tiers reject `nologo`), then anon.
    attempts: list = []
    if polli_token:
        attempts.append(("Pollinations (no-watermark)",
                         lambda c: _try_pollinations(c, prompt, width, height, model, polli_token, True)))
    if hf_token:
        attempts.append(("Hugging Face",
                         lambda c: _try_huggingface(c, prompt, width, height, hf_token)))
    if polli_token:
        attempts.append(("Pollinations (watermarked)",
                         lambda c: _try_pollinations(c, prompt, width, height, model, polli_token, False)))
    attempts.append(("Pollinations (anonymous)",
                     lambda c: _try_pollinations(c, prompt, width, height, "turbo", None, False)))

    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        for label, run in attempts:
            try:
                content, info = await run(client)
            except httpx.HTTPError as e:
                _log(f"{label} unavailable: network error: {e}")
                continue
            if content:
                if not label.startswith("Pollinations (no-watermark)") and not label.startswith("Hugging"):
                    _log(f"Used {label} for the design.", level="info")
                return _save(content, filename)
            _log(f"{label} unavailable: {info}")

    # Keyless, offline last resort — always succeeds so the pipeline never stalls.
    _log("All online image generators failed — used a built-in keyless design. "
         "The messages above show why each provider was rejected.")
    content = local_art.render_text_design(text or _phrase_from_prompt(prompt),
                                            width=width, height=height, transparent=transparent)
    return _save(content, filename)
