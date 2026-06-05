"""Brain router: pick a provider per task, track quota, fail over on rate limits.

- task="bulk"      -> prefer Groq (fast, high daily limit), fall back to Gemini.
- task="reasoning" -> prefer Gemini (stronger, long context), fall back to Groq.

Raises MissingKey only when NEITHER provider is configured, so the rest of the
app can give the user one clear "connect a brain" message.
"""
from __future__ import annotations

from app.brain import gemini_client, groq_client
from app.brain.errors import MissingKey, RateLimited, BrainError
from app.services import quota


def any_brain_available() -> bool:
    return gemini_client.available() or groq_client.available()


def _order(task: str) -> list[tuple[str, object]]:
    gemini = ("gemini", gemini_client)
    groq = ("groq", groq_client)
    return [groq, gemini] if task == "bulk" else [gemini, groq]


async def generate(prompt: str, system: str | None = None, *, task: str = "reasoning") -> str:
    if not any_brain_available():
        raise MissingKey(
            "No AI brain connected yet. Add a Google Gemini or Groq API key in Settings."
        )

    last_error: Exception | None = None
    for name, client in _order(task):
        if not client.available():
            continue
        if not quota.can_spend(name, 1):
            last_error = RateLimited(f"{name} daily free-tier budget reached")
            continue
        try:
            result = await client.generate(prompt, system)
            quota.spend(name, 1)
            return result
        except RateLimited as exc:
            last_error = exc
            continue  # try the next provider
        except (MissingKey, BrainError) as exc:
            last_error = exc
            continue

    raise (last_error or BrainError("All brain providers failed"))
