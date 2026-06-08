"""The agent team.

`REGISTRY` lists every agent instance. The scheduler iterates it to register jobs,
and the API uses it to run an agent on demand or toggle it on/off.
"""
from __future__ import annotations

from app.agents.onboarding_agent import OnboardingAgent
from app.agents.pod_agent import PodAgent
from app.agents.digital_agent import DigitalAgent
from app.agents.video_agent import VideoAgent
from app.agents.marketing_agent import MarketingAgent
from app.agents.bookkeeper_agent import BookkeeperAgent
from app.agents.optimizer_agent import OptimizerAgent

REGISTRY = {
    "onboarding": OnboardingAgent(),
    "pod": PodAgent(),
    "digital": DigitalAgent(),
    "video": VideoAgent(),
    "marketing": MarketingAgent(),
    "optimizer": OptimizerAgent(),
    "bookkeeper": BookkeeperAgent(),
}


def get(name: str):
    return REGISTRY.get(name)


def register_all_handlers() -> None:
    """Let agents register their approval resume-handlers at startup."""
    for agent in REGISTRY.values():
        agent.register_handlers()
