"""M7 tests — social handoffs, public SEO blog + subscribe, newsletter export.

Self-contained (no pytest): run with `python tests/test_m7.py`. The AI brain and the
network are monkeypatched; the public blog is exercised through the real ASGI app so
we prove it bypasses the PIN gate.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["AIT_DATA_DIR"] = tempfile.mkdtemp(prefix="ait_m7_")
os.environ["AIT_NO_TUNNEL"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import database          # noqa: E402
database.init_db()

import app.brain.router as brain      # noqa: E402

_JSON = json.dumps({
    "title": "Best Cat Mugs for Cat Lovers", "summary": "A guide to cat mugs.",
    "keywords": ["cat mug", "cat gift"],
    "sections": [{"heading": "Why cat mugs", "body": "Cats make mornings better."}],
    "cta": "Grab your cat mug today!",
    "subject": "New cat mugs just dropped!", "body": "Hi friend — we launched cat mugs. Enjoy!"})


async def fake_generate(prompt, system=None, *, task="reasoning"):
    return _JSON


brain.any_brain_available = lambda: True
brain.generate = fake_generate

from app.agents import REGISTRY, register_all_handlers  # noqa: E402
from app.integrations import social                     # noqa: E402
from app.orchestrator import approval                   # noqa: E402
from app.services import blog_export                    # noqa: E402

register_all_handlers()


def test_social_handoffs():
    _, pin = social.build_share_url("pinterest", text="Cool", hashtags=["#cat"],
                                    media="https://x.test/img.png", link="https://x.test/blog")
    assert "pinterest.com/pin/create" in pin and "media=" in pin, pin
    # Pinterest with NO public media must fall back to X (still works).
    label, url = social.build_share_url("pinterest", text="Cool", media=None)
    assert label == "X (Twitter)" and "twitter.com/intent" in url, url
    for plat, frag in [("threads", "threads.net"), ("bluesky", "bsky.app"),
                       ("tumblr", "tumblr.com")]:
        lbl, u = social.build_share_url(plat, text="Hi", link="https://x.test")
        assert frag in u, (plat, u)
    print("  ok: pinterest/threads/bluesky/tumblr handoffs (pinterest falls back without media)")


def test_blog_draft_then_publish():
    blog = REGISTRY["blog"]
    asyncio.run(blog.run(forced=True))
    draft = database.query_one("SELECT * FROM blog_posts WHERE status='draft' ORDER BY id DESC")
    assert draft, "a draft post should exist"
    pend = [a for a in approval.list_pending() if a["action_type"] == "blog_publish"]
    assert len(pend) == 1, f"one blog_publish approval expected, got {len(pend)}"
    asyncio.run(approval.resolve(pend[0]["id"], "approved"))
    pub = database.query_one("SELECT * FROM blog_posts WHERE status='published'")
    assert pub and pub["slug"] == draft["slug"], "post should be published"
    # body is escaped server-side (no raw script injection possible)
    assert "<script" not in (pub["body_html"] or "").lower()
    print(f"  ok: blog drafted -> approved -> published at /blog/{pub['slug']}")
    return pub


def test_public_blog_via_http(published):
    from starlette.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        # Public blog must be reachable with NO login/session.
        r = client.get("/blog")
        assert r.status_code == 200 and published["title"] in r.text, r.status_code
        r2 = client.get(f"/blog/{published['slug']}")
        assert r2.status_code == 200 and published["title"] in r2.text
        # The protected dashboard must still be gated (redirect to set-pin/login).
        r3 = client.get("/", follow_redirects=False)
        assert r3.status_code == 303 and r3.headers.get("location") in ("/login", "/set-pin")
        # Subscribe (public form), then dedupe.
        client.post("/blog/subscribe", data={"email": "Fan@Example.com"}, follow_redirects=False)
        client.post("/blog/subscribe", data={"email": "fan@example.com"}, follow_redirects=False)
    n = database.query_one("SELECT COUNT(*) AS n FROM email_subscribers")["n"]
    assert n == 1, f"subscriber should be deduped/normalized, got {n}"
    print("  ok: /blog public without login, dashboard still gated, subscribe dedupes")


def test_newsletter_export():
    database.execute(
        "INSERT INTO products (stream, platform, title, status) "
        "VALUES ('pod','printify','Cat Mug','live')")
    asyncio.run(REGISTRY["newsletter"].run(forced=True))
    pend = [a for a in approval.list_pending() if a["action_type"] == "newsletter_send"]
    assert len(pend) == 1, "one newsletter_send approval expected"
    asyncio.run(approval.resolve(pend[0]["id"], "approved"))
    folders = list((Path(os.environ["AIT_DATA_DIR"]) / "newsletters").glob("*/"))
    assert folders, "an exported newsletter folder should exist"
    f = folders[0]
    assert (f / "broadcast.txt").exists() and (f / "recipients.csv").exists()
    assert "fan@example.com" in (f / "recipients.csv").read_text()
    print("  ok: newsletter drafted -> approved -> exported draft + recipients.csv")


def test_blog_static_export():
    path, count = blog_export.export()
    assert count >= 1 and (path / "index.html").exists() and (path / "sitemap.xml").exists()
    print(f"  ok: static export wrote {count} post(s) + index + sitemap to {path}")


if __name__ == "__main__":
    test_social_handoffs()
    published = test_blog_draft_then_publish()
    test_public_blog_via_http(published)
    test_newsletter_export()
    test_blog_static_export()
    print("\nALL M7 TESTS PASSED")
