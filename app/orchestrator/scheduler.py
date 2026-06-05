"""Background scheduler that runs each enabled agent on its own interval.

Uses APScheduler's asyncio scheduler so agent coroutines run inside the app's event
loop. Agents themselves check `is_enabled()` (via BaseAgent.tick), so the jobs are
always registered but only do work when you've switched the agent on.
"""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import agents
from app.orchestrator import event_bus

_scheduler: AsyncIOScheduler | None = None


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    for name, agent in agents.REGISTRY.items():
        if agent.interval_minutes and agent.interval_minutes > 0:
            _scheduler.add_job(
                agent.tick, "interval", minutes=agent.interval_minutes,
                id=f"agent_{name}", max_instances=1, coalesce=True)
    _scheduler.start()
    event_bus.log("system", "Scheduler started — enabled agents will run on schedule.",
                  level="info")


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
