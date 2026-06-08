"""M6 tests — batch + multi-blueprint POD, the optimizer flywheel, research fallback.

Self-contained (no pytest needed): run with `python tests/test_m6.py`. External
integrations are monkeypatched, so nothing hits the network.
"""
import asyncio
import collections
import json
import os
import sys
import tempfile
from pathlib import Path

# Isolate to a throwaway DB and disable the tunnel BEFORE importing the app.
os.environ["AIT_DATA_DIR"] = tempfile.mkdtemp(prefix="ait_m6_")
os.environ["AIT_NO_TUNNEL"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config                       # noqa: E402
from app.db import database                  # noqa: E402

database.init_db()

import app.brain.router as brain             # noqa: E402
import app.integrations.printify as printify  # noqa: E402
import app.integrations.images as images     # noqa: E402
import app.integrations.research as research  # noqa: E402

calls = collections.Counter()
_pcounter = [0]

_CONCEPT_JSON = json.dumps({
    "niche": "cats", "audience": "cat lovers", "product_angle": "funny cat designs",
    "keywords": ["cat", "kitten", "meow"], "product_title": "Funny Cat Tee",
    "description": "A funny cat design.", "design_prompt": "a funny cartoon cat",
    "tags": ["cat", "funny"]})


async def fake_generate(prompt, system=None, *, task="reasoning"):
    calls["brain"] += 1
    return _CONCEPT_JSON


async def fake_image(prompt, **kw):
    calls["image"] += 1
    return Path("/tmp/x.png"), "/generated/x.png"


async def first_shop_id():
    return 1


async def find_blueprint(kw="t-shirt"):
    calls["find_blueprint"] += 1
    return {"id": abs(hash(kw)) % 1000, "title": kw}


async def first_print_provider(bp_id):
    return 10


async def list_variants(bp_id, pid):
    return [{"id": 1}, {"id": 2}]


async def upload_image(path, file_name=None):
    calls["upload"] += 1
    return "img123"


async def create_draft_product(shop_id, **kw):
    calls["create"] += 1
    _pcounter[0] += 1
    return {"id": f"prod_{_pcounter[0]}"}


async def publish_product(shop_id, product_id):
    calls["publish"] += 1


async def fake_brief():
    return {"niche": "cats", "audience": "cat lovers", "product_angle": "funny",
            "keywords": ["cat"], "_source": "trends+reddit"}


# --- wire the fakes in ------------------------------------------------------
brain.any_brain_available = lambda: True
brain.generate = fake_generate
images.generate = fake_image
printify.connected = lambda: True
printify.first_shop_id = first_shop_id
printify.find_blueprint = find_blueprint
printify.first_print_provider = first_print_provider
printify.list_variants = list_variants
printify.upload_image = upload_image
printify.create_draft_product = create_draft_product
printify.publish_product = publish_product
_real_demand_brief = research.demand_brief        # keep the real one for the fallback test
research.demand_brief = fake_brief

from app.agents.pod_agent import PodAgent          # noqa: E402
from app.agents.optimizer_agent import OptimizerAgent  # noqa: E402
from app.orchestrator import approval              # noqa: E402

N_BP = len(config.POD_BLUEPRINTS)
BATCH = config.BATCH["pod"]


_pod = PodAgent()
_pod.register_handlers()   # wire up the pod_publish resume-handler (startup does this in prod)


def test_pod_batch_multi_blueprint():
    asyncio.run(_pod.run(forced=True))
    assert calls["image"] == BATCH, f"one image per idea expected {BATCH}, got {calls['image']}"
    assert calls["upload"] == BATCH, "design uploaded once per idea"
    assert calls["create"] == BATCH * N_BP, f"expected {BATCH*N_BP} drafts, got {calls['create']}"

    products = database.query("SELECT * FROM products WHERE stream='pod'")
    assert len(products) == BATCH * N_BP, f"products rows: {len(products)}"

    pending = approval.list_pending()
    assert len(pending) == BATCH, f"one approval per idea expected {BATCH}, got {len(pending)}"
    assert all(len(a["payload"]["products"]) == N_BP for a in pending), "each approval = all SKUs"
    print(f"  ok: {BATCH} ideas x {N_BP} blueprints = {len(products)} SKUs, {len(pending)} approvals")


def test_approve_publishes_all_skus():
    first = approval.list_pending()[0]
    asyncio.run(approval.resolve(first["id"], "approved"))
    assert calls["publish"] == N_BP, f"approving one idea publishes all {N_BP}, got {calls['publish']}"
    live = database.query("SELECT * FROM products WHERE status='live'")
    assert len(live) == N_BP, f"live products: {len(live)}"
    print(f"  ok: approving one idea published all {N_BP} SKUs")
    return live


def test_optimizer_no_sales_is_honest():
    asyncio.run(OptimizerAgent().run(forced=True))
    reports = database.query("SELECT * FROM reports")
    assert reports and "No winners" in reports[-1]["title"], "honest no-sales report expected"
    obriefs = database.query("SELECT * FROM demand_briefs WHERE source='optimizer'")
    assert len(obriefs) == 0, "no winner brief should exist with zero sales"
    print("  ok: with no sales it reports 'no winners yet' and writes no brief")


def test_optimizer_with_sales_closes_loop(live):
    database.execute(
        "INSERT INTO sales (product_id, platform, external_id, gross_amount, fees, "
        "net_amount, occurred_at, source) VALUES (?,?,?,?,?,?,?,?)",
        (live[0]["id"], "printify", "printify:order_1", 24.99, 0, 24.99,
         "2026-06-01T00:00:00", "printify_order"))
    asyncio.run(OptimizerAgent().run(forced=True))
    obriefs = database.query("SELECT * FROM demand_briefs WHERE source='optimizer'")
    assert len(obriefs) == 1, f"one optimizer brief expected, got {len(obriefs)}"
    assert any(r["title"] == "What's working" for r in database.query("SELECT * FROM reports"))
    # the bookkeeper-owned 'source' is never 'manual'/'optimizer' on sales
    assert database.query("SELECT * FROM sales WHERE source='manual'") == []
    print("  ok: real sale -> 'what's working' report + winner-biased brief (flywheel closed)")


def test_research_falls_back_to_brain_only():
    async def empty(*a, **k):
        return []
    research.google_trends = empty
    research.reddit_hot = empty
    brief = asyncio.run(_real_demand_brief())
    assert brief["_source"] == "brain_only", f"expected brain_only, got {brief['_source']}"
    rows = database.query("SELECT * FROM demand_briefs WHERE source='brain_only'")
    assert len(rows) >= 1, "brain_only brief should be persisted"
    print("  ok: no live signals -> graceful brain-only brief")


if __name__ == "__main__":
    test_pod_batch_multi_blueprint()
    live = test_approve_publishes_all_skus()
    test_optimizer_no_sales_is_honest()
    test_optimizer_with_sales_closes_loop(live)
    test_research_falls_back_to_brain_only()
    print("\nALL M6 TESTS PASSED")
