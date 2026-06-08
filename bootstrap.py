"""Zero-setup bootstrap for AI Income Team.

Run by the double-click Start files (Start.command / Start.bat / start.sh). Uses
ONLY the Python standard library so it works before any dependencies exist. It:

  1. checks the Python version,
  2. creates an isolated virtual environment in .venv/ (first run only),
  3. installs the pinned dependencies (only when requirements.txt changes),
  4. launches the app via launcher.py (which opens your browser).

The user never has to touch a terminal or know what any of this means.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
DEPS_MARKER = VENV_DIR / ".deps_ok"
MIN_PYTHON = (3, 10)


def venv_python() -> Path:
    """Path to the Python interpreter inside our virtual environment."""
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def check_python_version() -> None:
    if sys.version_info < MIN_PYTHON:
        sys.exit(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required (you have "
            f"{sys.version_info.major}.{sys.version_info.minor}).\n"
            "Install the latest Python from https://www.python.org/downloads/ and try again.")


def create_venv() -> None:
    if venv_python().exists():
        return
    print("First-time setup: creating an isolated environment (this is normal)…")
    venv.create(VENV_DIR, with_pip=True)


def _requirements_hash() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def ensure_deps() -> None:
    """Install dependencies, skipping the work when nothing has changed."""
    want = _requirements_hash()
    if DEPS_MARKER.exists() and DEPS_MARKER.read_text().strip() == want:
        return
    print("Installing components (one-time; this can take a few minutes)…")
    py = str(venv_python())
    subprocess.check_call([py, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    subprocess.check_call([py, "-m", "pip", "install", "-r", str(REQUIREMENTS), "--quiet"])
    DEPS_MARKER.write_text(want)


def launch() -> int:
    print("Launching AI Income Team… your browser will open shortly.")
    return subprocess.call([str(venv_python()), str(ROOT / "launcher.py")])


def main() -> None:
    check_python_version()
    create_venv()
    ensure_deps()
    raise SystemExit(launch())


if __name__ == "__main__":
    main()
