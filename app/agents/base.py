"""Base class shared by every agent.

Subclasses implement `run()` (one work cycle) and optionally `register_handlers()`
(to wire up approval resume-handlers). The base handles enable/disable checks,
status updates, logging, and error capture so individual agents stay focused.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db import database
from app.memory import memory
from app.orchestrator import event_bus


class BaseAgent:
    name: str = "base"
    #: how often the scheduler runs this agent, in minutes (0 = never auto-run)
    interval_minutes: int = 0

    # --- state helpers -----------------------------------------------------
    def is_enabled(self) -> bool:
        row = database.query_one("SELECT enabled FROM agents WHERE name=?", (self.name,))
        return bool(row and row["enabled"])

    def set_enabled(self, enabled: bool) -> None:
        database.execute("UPDATE agents SET enabled=? WHERE name=?",
                         (1 if enabled else 0, self.name))
        self.log(f"{'Enabled' if enabled else 'Paused'} by you", level="info")

    def set_status(self, status: str) -> None:
        database.execute("UPDATE agents SET status=? WHERE name=?", (status, self.name))
        event_bus.emit("agent_status", agent=self.name, status=status)

    def log(self, message: str, level: str = "info", payload: dict | None = None) -> None:
        event_bus.log(self.name, message, level=level, payload=payload)

    # --- persistent memory -------------------------------------------------
    def remember(self, content: str, *, kind: str = "concept",
                 meta: dict | None = None) -> None:
        """Record something this agent made/learned, durably across restarts."""
        memory.remember(self.name, content, kind=kind, meta=meta)

    def recall(self, *, kind: str | None = None, limit: int = 25) -> list[dict]:
        return memory.recall(self.name, kind=kind, limit=limit)

    def avoid_repeats(self, *, kind: str = "concept", limit: int = 25) -> str:
        """Prompt fragment listing past creations so the brain makes something new."""
        return memory.avoid_repeats_clause(self.name, kind=kind, limit=limit)

    # --- mission / drive -----------------------------------------------------
    def mission_system(self, base_system: str) -> str:
        """Wrap a role prompt with the team's goal, playbook, and dopamine ledger."""
        from app.brain import mission
        return mission.compose(self.name, base_system)

    def record_win(self, what: str, meta: dict | None = None) -> None:
        """A success happened (publish/sale). Bank the dopamine and remember the pattern."""
        memory.remember(self.name, what, kind="win", meta=meta)
        self.log(f"+1 dopamine — WIN banked: {what}", level="success", payload=meta)

    # --- lifecycle ---------------------------------------------------------
    async def tick(self, *, forced: bool = False) -> None:
        """Run one cycle if enabled (or forced via the dashboard 'Run now' button)."""
        if not forced and not self.is_enabled():
            return
        self.set_status("running")
        database.execute("UPDATE agents SET last_run_at=? WHERE name=?",
                         (datetime.now(timezone.utc).isoformat(), self.name))
        try:
            await self.run(forced=forced)
            # If the run created a pending approval it may have set its own status.
            current = database.query_one("SELECT status FROM agents WHERE name=?", (self.name,))
            if current and current["status"] == "running":
                self.set_status("idle")
        except Exception as exc:
            self.set_status("error")
            self.log(f"Error: {exc}", level="error")

    # --- to override -------------------------------------------------------
    async def run(self, *, forced: bool = False) -> None:
        raise NotImplementedError

    def register_handlers(self) -> None:
        """Override to register approval resume-handlers. Default: nothing."""
        return None
