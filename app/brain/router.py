"""Brain router: pick a provider per task, track quota, fail over on rate limits.

- task="bulk"      -> prefer Groq (fast, high daily limit), fall back to Gemini.
- task="reasoning" -> prefer Gemini (stronger, long context), fall back to Groq.

Raises MissingKey only when NEITHER provider is configured, so the rest of the
app can give the user one clear "connect a brain" message.
"""
from __future__ import annotations

from app.brain import gemini_client, groq_client
from app.brain.errors import MissingKey, RateLimited, BrainError
from app.orchestrator import event_bus
from app.services import quota

_CLIENTS = {"gemini": gemini_client, "groq": groq_client}


def any_brain_available() -> bool:
    return gemini_client.available() or groq_client.available()


def _order(task: str) -> list[tuple[str, object]]:
    gemini = ("gemini", gemini_client)
    groq = ("groq", groq_client)
    return [groq, gemini] if task == "bulk" else [gemini, groq]


async def generate(prompt: str, system: str | None = None, *, task: str = "reasoning") -> str:
    """Backwards-compatible wrapper: returns just the reply text."""
    _, reply = await generate_detailed(prompt, system, task=task)
    return reply


async def generate_detailed(prompt: str, system: str | None = None, *,
                            task: str = "reasoning", only: str | None = None) -> tuple[str, str]:
    """Run the brain with failover. Returns (provider_used, reply).

    `only` restricts to a single provider ("gemini"/"groq") — used by the Settings
    "test backup brain" button to verify one provider directly.
    """
    if only:
        client = _CLIENTS.get(only)
        if client is None:
            raise BrainError(f"Unknown brain provider: {only}")
        if not client.available():
            raise MissingKey(f"{only.title()} is not connected — add its key in Settings.")
        providers = [(only, client)]
    else:
        if not any_brain_available():
            raise MissingKey(
                "No AI brain connected yet. Add a Google Gemini or Groq API key in Settings.")
        providers = _order(task)

    last_error: Exception | None = None
    failed_first = False
    for name, client in providers:
        if not client.available():
            continue
        if not quota.can_spend(name, 1):
            last_error = RateLimited(f"{name} daily free-tier budget reached")
            event_bus.log("brain", f"{name} daily free-tier budget reached — trying backup…",
                          level="warn")
            failed_first = True
            continue
        try:
            result = await client.generate(prompt, system)
            quota.spend(name, 1)
            if failed_first:
                event_bus.log("brain", f"{name} backup answered.", level="success")
            return name, result
        except (RateLimited, MissingKey, BrainError) as exc:
            last_error = exc
            event_bus.log("brain", f"{name} brain unavailable ({exc}) — trying backup…",
                          level="warn")
            failed_first = True
            continue

    raise (last_error or BrainError("All brain providers failed"))
