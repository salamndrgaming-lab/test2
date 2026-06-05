"""Groq free-tier client (OpenAI-compatible REST). Great for fast, high-volume tasks."""
from __future__ import annotations

import httpx

from app import config
from app.brain.errors import MissingKey, RateLimited, BrainError
from app.vault import vault

_URL = "https://api.groq.com/openai/v1/chat/completions"


def available() -> bool:
    return vault.has_secret("groq_api_key")


async def generate(prompt: str, system: str | None = None, *, model: str | None = None) -> str:
    key = vault.get_secret("groq_api_key")
    if not key:
        raise MissingKey("Groq API key not set")
    model = model or config.GROQ_MODEL

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            _URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": messages},
        )

    if resp.status_code == 429:
        raise RateLimited("Groq rate limit hit")
    if resp.status_code >= 400:
        raise BrainError(f"Groq error {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise BrainError(f"Unexpected Groq response: {str(data)[:300]}") from exc
