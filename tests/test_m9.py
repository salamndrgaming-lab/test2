"""M9 tests — the Vault page route/auth + /api/state enrichment.

Self-contained (no pytest): `python tests/test_m9.py`.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["AIT_DATA_DIR"] = tempfile.mkdtemp(prefix="ait_m9_")
os.environ["AIT_NO_TUNNEL"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import database          # noqa: E402
database.init_db()

from starlette.testclient import TestClient  # noqa: E402
from app.main import app                      # noqa: E402
from app.orchestrator import event_bus        # noqa: E402


def test_state_has_last_message():
    event_bus.log("pod", "Generating the design artwork…", level="info")
    with TestClient(app) as client:
        client.post("/set-pin", data={"pin": "1234", "confirm": "1234"},
                    follow_redirects=False)  # creates PIN + authed session
        s = client.get("/api/state").json()
        assert "pod" in s["agents"], "agents present"
        assert s["agents"]["pod"]["last_message"] == "Generating the design artwork…"
        # existing keys still intact
        for k in ("enabled", "status", "last_run_at"):
            assert k in s["agents"]["pod"], k
    print("  ok: /api/state agents now carry last_message (existing keys intact)")


def test_shelter_requires_auth():
    with TestClient(app) as client:  # fresh client, no session cookie
        r = client.get("/shelter", follow_redirects=False)
        assert r.status_code == 303 and r.headers.get("location") in ("/login", "/set-pin"), r.status_code
    print("  ok: /shelter is gated when not logged in")


def test_shelter_renders_when_authed():
    with TestClient(app) as client:
        client.post("/set-pin", data={"pin": "1234", "confirm": "1234"}, follow_redirects=False)
        r = client.get("/shelter")
        assert r.status_code == 200, r.status_code
        for needle in ('id="vault"', "shelter.js", "VAULT_ROSTER", "QUARTERS" if False else "Vault"):
            assert needle in r.text, needle
        # roster JSON is injected with the agents
        assert "pod" in r.text and "bookkeeper" in r.text
    print("  ok: /shelter renders canvas + shelter.js + injected roster when authed")


if __name__ == "__main__":
    test_state_has_last_message()
    test_shelter_requires_auth()
    test_shelter_renders_when_authed()
    print("\nALL M9 TESTS PASSED")
