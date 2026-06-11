"""M10 tests — persistent agent memory + image-provider fallback.

Self-contained (no pytest): `python tests/test_m10.py`.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["AIT_DATA_DIR"] = tempfile.mkdtemp(prefix="ait_m10_")
os.environ["AIT_NO_TUNNEL"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import database          # noqa: E402
database.init_db()

from starlette.testclient import TestClient  # noqa: E402
from app.main import app                      # noqa: E402
from app.memory import memory                 # noqa: E402
from app.integrations import images           # noqa: E402


def test_memory_persists_and_recalls():
    memory.remember("pod", "Alpha Concept", meta={"niche": "x"})
    memory.remember("pod", "Beta Concept")
    memory.remember("blog", "Gamma Post")
    assert memory.count() >= 3
    assert memory.count("pod") == 2
    pod = [m["content"] for m in memory.recall("pod")]
    assert pod == ["Beta Concept", "Alpha Concept"], pod  # most-recent first
    print("  ok: memories persist, count + recency-ordered recall work")


def test_avoid_repeats_clause_scoped_per_agent():
    clause = memory.avoid_repeats_clause("pod")
    assert "Alpha Concept" in clause and "Beta Concept" in clause
    assert "Gamma Post" not in clause          # other agents' memories excluded
    assert memory.avoid_repeats_clause("kdp") == ""  # nothing remembered yet
    print("  ok: avoid-repeats clause is per-agent and empty when nothing stored")


def test_memory_page_renders_authed():
    with TestClient(app) as client:
        client.post("/set-pin", data={"pin": "1234", "confirm": "1234"},
                    follow_redirects=False)
        r = client.get("/memory")
        assert r.status_code == 200, r.status_code
        assert "Alpha Concept" in r.text and 'href="/memory"' in r.text
    print("  ok: /memory page renders entries when authed")


def test_image_falls_back_to_local_design_without_tokens():
    # No tokens configured → online attempts fail, but the keyless local designer
    # always produces a real PNG so the pipeline never stalls (M11 covers this in
    # depth; here we just confirm M10's expectation flipped from raise -> succeed).
    path, web = asyncio.run(images.generate("a red apple", width=64, height=64,
                                            text="Red Apple"))
    assert path.exists() and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", path
    assert web.startswith("/generated/"), web
    print("  ok: image generation falls back to a local keyless PNG (no token needed)")


if __name__ == "__main__":
    test_memory_persists_and_recalls()
    test_avoid_repeats_clause_scoped_per_agent()
    test_memory_page_renders_authed()
    test_image_falls_back_to_local_design_without_tokens()
    print("\nALL M10 TESTS PASSED")
