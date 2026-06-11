"""Persistent agent memory.

A thin, durable store on top of the `agent_memory` SQLite table. Agents record
short memories (a concept title, a learning) and read recent ones back across
runs and restarts, so the team doesn't repeat itself and can build on the past.

Deliberately simple: recency-ordered recall, no embeddings. The volumes here are
small (a handful of ideas per run) so plain SQL is the right tool.
"""
from __future__ import annotations

import json

from app.db import database


def remember(agent: str, content: str, *, kind: str = "concept",
             meta: dict | None = None) -> int:
    """Store one memory. Returns its row id."""
    content = (content or "").strip()
    if not content:
        return 0
    return database.execute(
        "INSERT INTO agent_memory (agent, kind, content, meta_json) VALUES (?,?,?,?)",
        (agent, kind, content, json.dumps(meta) if meta else None))


def recall(agent: str | None = None, *, kind: str | None = None,
           limit: int = 25) -> list[dict]:
    """Most-recent memories first. Filterable by agent and/or kind."""
    where, params = [], []
    if agent:
        where.append("agent=?"); params.append(agent)
    if kind:
        where.append("kind=?"); params.append(kind)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)
    return database.query(
        f"SELECT id, agent, kind, content, meta_json, created_at FROM agent_memory"
        f"{clause} ORDER BY id DESC LIMIT ?", params)


def recent_contents(agent: str, *, kind: str = "concept", limit: int = 25) -> list[str]:
    """Just the text of recent memories — handy for prompt context."""
    return [r["content"] for r in recall(agent, kind=kind, limit=limit)]


def avoid_repeats_clause(agent: str, *, kind: str = "concept", limit: int = 25) -> str:
    """A prompt fragment listing recent items so the brain makes something new.

    Returns "" when there's nothing remembered yet.
    """
    items = recent_contents(agent, kind=kind, limit=limit)
    if not items:
        return ""
    joined = "; ".join(items)
    return (f" You have ALREADY created these — do NOT repeat or closely imitate any "
            f"of them, invent something clearly different: {joined}.")


def count(agent: str | None = None) -> int:
    sql = "SELECT COUNT(*) AS n FROM agent_memory"
    params: list = []
    if agent:
        sql += " WHERE agent=?"; params.append(agent)
    row = database.query_one(sql, params)
    return int(row["n"]) if row else 0
