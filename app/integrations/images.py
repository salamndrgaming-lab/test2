"""Image generation with automatic provider fallback.

Pollinations.ai used to allow anonymous use, but it now gates generation behind a
registered token and returns HTTP 402 ("Payment Required") otherwise — there is
no longer a truly anonymous free endpoint. So we support two FREE providers and
try whatever the user has connected, in order:

  1. Pollinations (token)        — free token from https://auth.pollinations.ai
  2. Hugging Face (token)        — free token from https://huggingface.co/settings/tokens
  3. Pollinations (anonymous)    — last-ditch, in case a tier still allows it

Both tokens are free (no credit card). The user only needs ONE of them. If none
is configured and the anonymous attempt fails, we raise a clear, actionable error.

Saves PNGs into data/generated/ and returns (absolute_path, web_path).
"""
from __future__ import annotations

import time
import urllib.parse
from pathlib import Path

import httpx

from app import config
from app.vault import vault

_POLLI = "https://image.pollinations.ai/prompt/"
_HF = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
# Statuses meaning "not allowed / busy for me" — move on to the next provider.
_RECOVERABLE = {401, 402, 403, 404, 429, 500, 502, 503}


async def _try_pollinations(client, prompt, width, height, model, token):
    params = {"width": width, "height": height, "seed": int(time.time()),
              "referrer": "ai-income-team", "model": model}
    headers = {"User-Agent": "Mozilla/5.0 (AI-Income-Team)"}
    if token:
        params["nologo"] = "true"
        params["token"] = token
        headers["Authorization"] = f"Bearer {token}"
    resp = await client.get(_POLLI + urllib.parse.quote(prompt), params=params, headers=headers)
    return resp.content if _is_image(resp) else None, _describe(resp)


async def _try_huggingface(client, prompt, width, height, token):
    if not token:
        return None, "no Hugging Face token"
    resp = await client.post(
        _HF, headers={"Authorization": f"Bearer {token}"},
        json={"inputs": prompt, "parameters": {"width": width, "height": height}})
    return resp.content if _is_image(resp) else None, _describe(resp)


def _is_image(resp) -> bool:
    return resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image")


def _describe(resp) -> str:
    return f"HTTP {resp.status_code} ({resp.headers.get('content-type', 'no content-type')})"


async def generate(prompt: str, *, width: int = 1024, height: int = 1024,
                   model: str = "flux", filename: str | None = None) -> tuple[Path, str]:
    config.ensure_dirs()
    polli_token = vault.get_secret("pollinations_token")
    hf_token = vault.get_secret("huggingface_token")

    # (label, awaitable-factory) in priority order. Token providers first.
    attempts: list = []
    if polli_token:
        attempts.append(("Pollinations",
                         lambda c: _try_pollinations(c, prompt, width, height, model, polli_token)))
    if hf_token:
        attempts.append(("Hugging Face",
                         lambda c: _try_huggingface(c, prompt, width, height, hf_token)))
    attempts.append(("Pollinations (anonymous)",
                     lambda c: _try_pollinations(c, prompt, width, height, "turbo", None)))

    last = "no attempts made"
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        for label, run in attempts:
            try:
                content, info = await run(client)
            except httpx.HTTPError as e:
                last = f"{label}: network error: {e}"
                continue
            if content:
                name = filename or f"design_{int(time.time()*1000)}.png"
                out_path = config.GENERATED_DIR / name
                out_path.write_bytes(content)
                return out_path, f"/generated/{name}"
            last = f"{label}: {info}"

    raise RuntimeError(
        f"Image generation failed ({last}). Free image generators now require a free "
        "token — add ONE in Settings: Pollinations (auth.pollinations.ai) or Hugging "
        "Face (huggingface.co/settings/tokens). No credit card needed.")
