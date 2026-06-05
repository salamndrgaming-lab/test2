"""Shared exceptions for the brain layer."""


class BrainError(Exception):
    """Generic brain failure (bad response, network, etc.)."""


class MissingKey(BrainError):
    """No API key configured for the requested provider."""


class RateLimited(BrainError):
    """Provider returned HTTP 429 — caller should fail over or back off."""
