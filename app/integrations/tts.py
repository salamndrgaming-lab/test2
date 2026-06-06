"""Free, offline text-to-speech via Piper.

Piper runs locally (no API key, no per-use cost). The voice model is a small
ONNX file downloaded once into data/voices/ on first use. If the model can't be
fetched (e.g. no internet on first run), callers should fall back gracefully.
"""
from __future__ import annotations

import time
import wave
from pathlib import Path

from app import config

# A small, natural English voice — good quality, ~60MB, fast on CPU.
DEFAULT_VOICE = "en_US-amy-low"


class TTSUnavailable(Exception):
    """Raised when narration can't be produced (engine or voice unavailable)."""


def available() -> bool:
    try:
        import piper  # noqa: F401
        return True
    except Exception:
        return False


def ensure_voice(voice: str = DEFAULT_VOICE) -> Path:
    """Return the local path to the voice model, downloading it once if needed."""
    config.ensure_dirs()
    model = config.VOICES_DIR / f"{voice}.onnx"
    if model.exists():
        return model
    try:
        from piper.download_voices import download_voice
        download_voice(voice, config.VOICES_DIR)
    except Exception as exc:  # network blocked, voice renamed, etc.
        raise TTSUnavailable(f"Couldn't download the '{voice}' voice: {exc}") from exc
    if not model.exists():
        raise TTSUnavailable(f"Voice '{voice}' did not download correctly.")
    return model


def synthesize(text: str, *, voice: str = DEFAULT_VOICE,
               filename: str | None = None) -> tuple[Path, float]:
    """Render `text` to a WAV file. Returns (path, duration_seconds)."""
    if not available():
        raise TTSUnavailable("Piper TTS is not installed.")
    model = ensure_voice(voice)
    from piper import PiperVoice

    name = filename or f"narration_{int(time.time()*1000)}.wav"
    out_path = config.GENERATED_DIR / name
    try:
        pv = PiperVoice.load(model)
        with wave.open(str(out_path), "wb") as wf:
            pv.synthesize_wav(text, wf)
    except Exception as exc:
        raise TTSUnavailable(f"Narration failed: {exc}") from exc
    return out_path, wav_duration(out_path)


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as wf:
        return wf.getnframes() / float(wf.getframerate() or 1)
