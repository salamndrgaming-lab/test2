"""Central configuration: paths, ports, and model routing.

Everything is derived from the project root so the app is fully portable and
needs zero setup on the user's machine. Folders are created on first run.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Paths -----------------------------------------------------------------
# Project root = the folder that contains the `app/` package.
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AIT_DATA_DIR", ROOT_DIR / "data"))
GENERATED_DIR = DATA_DIR / "generated"      # designs, audio, video drafts live here
VOICES_DIR = DATA_DIR / "voices"            # downloaded Piper TTS voice models
DB_PATH = DATA_DIR / "app.db"
VAULT_FILE = DATA_DIR / "vault.enc"         # encrypted-at-rest secrets fallback
VAULT_KEY_FILE = DATA_DIR / ".vault_key"    # used only if OS keyring is unavailable

WEB_DIR = Path(__file__).resolve().parent / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

# --- Server ----------------------------------------------------------------
HOST = os.environ.get("AIT_HOST", "127.0.0.1")
PORT = int(os.environ.get("AIT_PORT", "8765"))

# --- Identity (used for OS keyring entries) --------------------------------
APP_NAME = "AI Income Team"
KEYRING_SERVICE = "ai-income-team"

# --- LLM "brain" routing ---------------------------------------------------
# Groq handles high-volume short tasks; Gemini handles long-context reasoning.
# The router prefers the cheaper option per task and fails over on rate limits.
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_MODEL_LIGHT = "gemini-2.5-flash-lite"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_MODEL_LIGHT = "llama-3.1-8b-instant"

# Conservative free-tier daily ceilings the app self-throttles against.
# (Real limits per provider docs; we stay safely under them.)
QUOTA_LIMITS = {
    "gemini": 200,        # requests/day (free flash, kept conservative)
    "groq": 10000,        # requests/day
    "youtube": 10000,     # quota units/day
}

# Names of secrets stored in the vault. Keep in sync with the onboarding wizard.
SECRET_KEYS = {
    "gemini_api_key": "Google Gemini API key",
    "groq_api_key": "Groq API key",
    "printify_api_token": "Printify API token",
    "gumroad_access_token": "Gumroad access token",
}


def ensure_dirs() -> None:
    """Create runtime folders if they do not exist yet (idempotent)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
