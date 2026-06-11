"""Setup agent: drives the onboarding wizard and reports what's connected.

It cannot create accounts for the user (that violates provider ToS — captchas,
phone verification), so it provides exact step-by-step guidance and a secure
paste-the-key flow instead. Once keys are pasted, the other agents run on their own.
"""
from __future__ import annotations

from app.agents.base import BaseAgent
from app.brain import router as brain
from app.integrations import printify
from app.vault import vault


# Each step: what the user does once, and which secret it produces.
WIZARD_STEPS = [
    {
        "key": "gemini_api_key",
        "title": "Connect the AI brain (Google Gemini) — free",
        "why": "Powers the agents' thinking. Free tier, no credit card.",
        "url": "https://aistudio.google.com/app/apikey",
        "steps": [
            "Open the link and sign in with any Google account.",
            "Click 'Create API key'.",
            "Copy the key and paste it below.",
        ],
    },
    {
        "key": "groq_api_key",
        "title": "Connect a backup brain (Groq) — free, optional",
        "why": "Fast, high-volume backup so the agents keep working if Gemini is busy.",
        "url": "https://console.groq.com/keys",
        "steps": [
            "Open the link and sign up with email (no card).",
            "Click 'Create API Key', copy it, paste it below.",
        ],
    },
    {
        "key": "printify_api_token",
        "title": "Connect your print-on-demand store (Printify) — free",
        "why": "Where the print-on-demand agent builds your products. Free; you only pay per item when it sells.",
        "url": "https://printify.com/app/account/api",
        "steps": [
            "Create a free Printify account and a shop (their free 'Pop-Up Store' works).",
            "Go to Account → Connections (the link above) and click 'Generate' a new Personal Access Token.",
            "Copy the token and paste it below.",
        ],
    },
    {
        "key": "gumroad_access_token",
        "title": "Connect Gumroad (digital products) — free",
        "why": "Lets the bookkeeper track real sales of your digital products. Free to start (~10% per sale).",
        "url": "https://app.gumroad.com/settings/advanced",
        "steps": [
            "Create a free Gumroad account.",
            "Open Settings → Advanced (the link above) and under 'Applications' create an application.",
            "Generate an access token for it, copy the token, and paste it below.",
        ],
    },
    {
        "key": "pollinations_token",
        "title": "Image generator token (Pollinations) — free, optional",
        "why": "Designs still generate without this, but a free token unlocks the "
               "higher-quality model and removes the small watermark.",
        "url": "https://auth.pollinations.ai",
        "steps": [
            "Open the link and sign in (GitHub works).",
            "Create/copy a token from your dashboard.",
            "Paste it below. (Leave blank to keep using the free anonymous tier.)",
        ],
    },
]


class OnboardingAgent(BaseAgent):
    name = "onboarding"
    interval_minutes = 0  # runs on demand / when the wizard is opened

    def wizard_status(self) -> list[dict]:
        """Return the wizard steps annotated with current connection state."""
        connected = vault.connection_status()
        out = []
        for step in WIZARD_STEPS:
            s = dict(step)
            s["connected"] = connected.get(step["key"], False)
            out.append(s)
        return out

    def overall_ready(self) -> dict:
        return {
            "brain_ready": brain.any_brain_available(),
            "printify_ready": printify.connected(),
        }

    async def run(self, *, forced: bool = False) -> None:
        status = self.overall_ready()
        if status["brain_ready"] and status["printify_ready"]:
            self.log("Setup looks complete — agents are ready to work.", level="success")
        else:
            missing = []
            if not status["brain_ready"]:
                missing.append("an AI brain key (Gemini or Groq)")
            if not status["printify_ready"]:
                missing.append("your Printify token")
            self.log("Setup still needs: " + ", ".join(missing) +
                     ". Open Settings to finish.", level="warn")
