"""M11 tests — brain failover/attribution, keyless local art, image fallback.

Self-contained (no pytest): `python tests/test_m11.py`.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["AIT_DATA_DIR"] = tempfile.mkdtemp(prefix="ait_m11_")
os.environ["AIT_NO_TUNNEL"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import database          # noqa: E402
database.init_db()

from app.brain import router, gemini_client, groq_client  # noqa: E402
from app.brain.errors import BrainError, MissingKey       # noqa: E402
from app.integrations import images, local_art            # noqa: E402


def _restore(saved):
    gemini_client.available, gemini_client.generate = saved[0], saved[1]
    groq_client.available, groq_client.generate = saved[2], saved[3]


def test_failover_to_groq_with_attribution():
    saved = (gemini_client.available, gemini_client.generate,
             groq_client.available, groq_client.generate)
    try:
        gemini_client.available = lambda: True
        groq_client.available = lambda: True

        async def gem_fail(prompt, system=None, **k):  # simulate Gemini 503 / timeout
            raise BrainError("Gemini error 503: high demand")

        async def groq_ok(prompt, system=None, **k):
            return "hello from groq"

        gemini_client.generate = gem_fail
        groq_client.generate = groq_ok

        used, reply = asyncio.run(router.generate_detailed("hi", task="reasoning"))
        assert used == "groq" and reply == "hello from groq", (used, reply)
        print("  ok: Gemini failure fails over to Groq (provider attributed)")
    finally:
        _restore(saved)


def test_only_provider_forced_and_missing():
    saved = (gemini_client.available, gemini_client.generate,
             groq_client.available, groq_client.generate)
    try:
        gemini_client.available = lambda: True
        groq_client.available = lambda: False  # Groq not connected

        async def gem_ok(prompt, system=None, **k):
            return "from gemini"

        gemini_client.generate = gem_ok
        # only='gemini' forces Gemini even on a "bulk" task (which normally prefers Groq)
        used, reply = asyncio.run(router.generate_detailed("hi", task="bulk", only="gemini"))
        assert used == "gemini" and reply == "from gemini", (used, reply)

        # forcing the disconnected backup raises a clear MissingKey
        try:
            asyncio.run(router.generate_detailed("hi", only="groq"))
            assert False, "expected MissingKey"
        except MissingKey:
            pass
        print("  ok: only=<provider> forces one brain; forcing a missing one errors cleanly")
    finally:
        _restore(saved)


def test_local_art_returns_png():
    for transparent in (True, False):
        data = local_art.render_text_design("Mamba Mentality Tee", width=256, height=256,
                                             transparent=transparent)
        assert data[:8] == b"\x89PNG\r\n\x1a\n", "valid PNG signature"
        assert len(data) > 200, "non-trivial image"
    print("  ok: local_art renders valid PNGs (transparent + gradient)")


def test_images_local_fallback_without_tokens():
    # No tokens set + no network in tests → must still return a real saved PNG.
    path, web = asyncio.run(images.generate("a minimalist vector graphic of a cat",
                                            width=128, height=128, text="Cat Lover"))
    assert path.exists() and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", path
    assert web.startswith("/generated/"), web
    print("  ok: images.generate falls back to a keyless local design (never raises)")


if __name__ == "__main__":
    test_failover_to_groq_with_attribution()
    test_only_provider_forced_and_missing()
    test_local_art_returns_png()
    test_images_local_fallback_without_tokens()
    print("\nALL M11 TESTS PASSED")
