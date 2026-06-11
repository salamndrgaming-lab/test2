"""Free image generation via Pollinations.ai.

Anonymous use still works, but Pollinations now gates its premium options — the
`flux` model and the `nologo` (watermark-off) flag — behind a registered token,
returning HTTP 402 ("Payment Required") when they're requested without one.

To stay robust we try a sequence of strategies, best first, and fall back to the
free anonymous tier automatically:

  1. (only if a token is configured) flux + no-watermark, authenticated;
  2. the free `turbo` model, no watermark flag;
  3. a bare default request.

The token is OPTIONAL and free — create one at https://auth.pollinations.ai and
paste it into Settings to unlock the better model and remove the watermark.

Saves PNGs into data/generated/ and returns (absolute_path, web_path).
"""
from __future__ import annotations

import time
import urllib.parse
from pathlib import Path

import httpx

from app import config
from app.vault import vault

_BASE = "https://image.pollinations.ai/prompt/"
_FREE_MODEL = "turbo"  # usable on the anonymous tier without a token
# Statuses that mean "this strategy isn't allowed for me" — try a cheaper one.
_RETRYABLE = {401, 402, 403, 429, 500, 502, 503}


def _strategies(model: str, base: dict, headers: dict, token: str | None) -> list[tuple[dict, dict]]:
    """Ordered (params, headers) attempts, premium first then free fallbacks."""
    out: list[tuple[dict, dict]] = []
    if token:
        out.append(({**base, "model": model, "nologo": "true", "token": token},
                    {**headers, "Authorization": f"Bearer {token}"}))
    out.append(({**base, "model": _FREE_MODEL}, headers))  # free anonymous tier
    out.append((dict(base), headers))                       # bare default
    return out


async def generate(prompt: str, *, width: int = 1024, height: int = 1024,
                   model: str = "flux", filename: str | None = None) -> tuple[Path, str]:
    config.ensure_dirs()
    encoded = urllib.parse.quote(prompt)
    token = vault.get_secret("pollinations_token")

    base = {"width": width, "height": height, "seed": int(time.time()),
            "referrer": "ai-income-team"}
    headers = {"User-Agent": "Mozilla/5.0 (AI-Income-Team)"}

    last = "no attempts made"
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        for params, hdrs in _strategies(model, base, headers, token):
            try:
                resp = await client.get(_BASE + encoded, params=params, headers=hdrs)
            except httpx.HTTPError as e:
                last = f"network error: {e}"
                continue
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200 and ctype.startswith("image"):
                name = filename or f"design_{int(time.time()*1000)}.png"
                out_path = config.GENERATED_DIR / name
                out_path.write_bytes(resp.content)
                return out_path, f"/generated/{name}"
            last = f"HTTP {resp.status_code} ({ctype or 'no content-type'})"
            if resp.status_code not in _RETRYABLE:
                break  # a non-recoverable error (e.g. 400 bad prompt) — stop early

    hint = ("" if token else
            " Tip: add a free Pollinations token in Settings "
            "(https://auth.pollinations.ai) to unlock the better model and remove "
            "the watermark.")
    raise RuntimeError(f"Image generation failed ({last}).{hint}")
