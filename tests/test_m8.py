"""M8 tests — Etsy/KDP handoffs, low-content interior PDF, honest manual revenue.

Self-contained (no pytest): `python tests/test_m8.py`. Brain + images are monkeypatched.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["AIT_DATA_DIR"] = tempfile.mkdtemp(prefix="ait_m8_")
os.environ["AIT_NO_TUNNEL"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import database          # noqa: E402
database.init_db()

import app.brain.router as brain      # noqa: E402
import app.integrations.images as images  # noqa: E402

_JSON = json.dumps({
    "title": "Gratitude Journal", "subtitle": "Daily", "niche": "wellness",
    "page_style": "lined", "pages": 120,
    "keywords": ["journal", "gratitude", "wellness", "gift", "planner"],
    "description": "A lovely journal.", "cover_prompt": "calm pattern",
    "product_type": "guide", "listing_description": "Great guide.", "price_usd": 12,
    "tags": list("abcdefghijklmno"),  # 15 tags -> Etsy must clamp to 13
    "sections": [{"heading": "Intro", "body": "Hello world.\n\nSecond paragraph."}]})


async def fake_generate(prompt, system=None, *, task="reasoning"):
    return _JSON


async def fake_image(prompt, **kw):
    return Path("/tmp/x.png"), "/generated/x.png"


brain.any_brain_available = lambda: True
brain.generate = fake_generate
images.generate = fake_image

from app.agents import REGISTRY, register_all_handlers  # noqa: E402
from app.integrations import documents, etsy, kdp        # noqa: E402
from app.orchestrator import approval                     # noqa: E402
from app.services import revenue                          # noqa: E402
from app.web import routes_api                            # noqa: E402

register_all_handlers()


def test_etsy_tag_clamping():
    tags = etsy.listing_tags(["x" * 30] + ["t"] * 20)
    assert len(tags) == 13 and all(len(t) <= 20 for t in tags), tags
    assert etsy.ADD_LISTING_URL.startswith("https://www.etsy.com")
    print("  ok: Etsy tags clamped to 13 x <=20 chars; handoff URL present")


def test_interior_pdf_generation():
    path, web = documents.generate_interior("Test Journal", page_style="dot", pages=10)
    assert path.exists() and path.stat().st_size > 1000 and web.startswith("/generated/")
    print(f"  ok: KDP interior PDF generated ({path.stat().st_size} bytes)")


def test_kdp_draft_then_publish():
    asyncio.run(REGISTRY["kdp"].run(forced=True))
    pend = [a for a in approval.list_pending() if a["action_type"] == "kdp_publish"]
    assert len(pend) == 1, "one kdp_publish approval expected"
    assert pend[0]["payload"]["handoff_url"] == kdp.CREATE_PAPERBACK_URL
    asyncio.run(approval.resolve(pend[0]["id"], "approved"))
    live = database.query("SELECT * FROM products WHERE stream='kdp' AND status='live'")
    assert len(live) == 1, "KDP product should be live after approval"
    print("  ok: KDP book drafted -> approved -> live (stream='kdp')")


def test_digital_offers_etsy_handoff():
    asyncio.run(REGISTRY["digital"].run(forced=True))
    pend = [a for a in approval.list_pending() if a["action_type"] == "digital_publish"]
    assert pend, "digital_publish approval expected"
    extra = pend[0]["payload"].get("extra_handoffs", [])
    assert any(h["platform"] == "Etsy" for h in extra), extra
    assert pend[0]["payload"]["handoff_url"]  # Gumroad still the primary handoff
    print("  ok: digital product offers BOTH Gumroad and Etsy handoffs")


def test_manual_revenue_honest_and_scoped():
    before = revenue.totals()["net"]
    asyncio.run(routes_api.add_manual_revenue(amount=10.0, label="Etsy", fees=2.0,
                                              occurred_at="2026-06-01"))
    row = database.query_one("SELECT * FROM sales WHERE source='manual'")
    assert row and row["net_amount"] == 8.0 and row["platform"] == "Etsy"
    assert abs(revenue.totals()["net"] - (before + 8.0)) < 0.001, "manual sale counts in totals"

    # A non-manual (API-synced) sale must NOT be deletable via the manual endpoint.
    api_id = database.execute(
        "INSERT INTO sales (platform, external_id, gross_amount, net_amount, source) "
        "VALUES ('printify','printify:o9',5,5,'printify_order')")
    asyncio.run(routes_api.delete_manual_revenue(api_id))
    assert database.query_one("SELECT 1 FROM sales WHERE id=?", (api_id,)), "API sale must remain"

    # The manual one IS deletable.
    asyncio.run(routes_api.delete_manual_revenue(row["id"]))
    assert database.query("SELECT * FROM sales WHERE source='manual'") == []
    print("  ok: manual sale counts honestly, is deletable, and can't delete API-synced sales")


if __name__ == "__main__":
    test_etsy_tag_clamping()
    test_interior_pdf_generation()
    test_kdp_draft_then_publish()
    test_digital_offers_etsy_handoff()
    test_manual_revenue_honest_and_scoped()
    print("\nALL M8 TESTS PASSED")
