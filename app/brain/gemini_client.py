"""Google Gemini free-tier client (direct REST, no SDK to avoid version churn).

Free tier allows commercial use. Never send secrets/PII through it — free-tier
content may be used to improve Google's models.
"""
from __future__ import annotations

import httpx

from app import config
from app.brain.errors import MissingKey, RateLimited, BrainError
from app.vault import vault

_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def available() -> bool:
    return vault.has_secret("gemini_api_key")


async def generate(prompt: str, system: str | None = None, *, model: str | None = None) -> str:
    key = vault.get_secret("gemini_api_key")
    if not key:
        raise MissingKey("Gemini API key not set")
    model = model or config.GEMINI_MODEL

    body: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    async with httpx.AsyncClient(timeout=90) as client:
        try:
            resp = await client.post(_URL.format(model=model), params={"key": key}, json=body)
        except httpx.HTTPError as exc:
            # Timeouts / connection drops must be catchable so the router fails over.
            raise BrainError(f"Gemini network error: {exc}") from exc

    if resp.status_code == 429:
        raise RateLimited("Gemini rate limit hit")
    if resp.status_code >= 400:
        raise BrainError(f"Gemini error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        raise BrainError(f"Unexpected Gemini response: {str(data)[:300]}") from exc
