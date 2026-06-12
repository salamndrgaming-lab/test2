"""M12 tests — the mission/drive layer: goal, playbook, dopamine ledger, lessons.

Self-contained (no pytest): `python tests/test_m12.py`.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["AIT_DATA_DIR"] = tempfile.mkdtemp(prefix="ait_m12_")
os.environ["AIT_NO_TUNNEL"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import database          # noqa: E402
database.init_db()

from app.brain import mission                  # noqa: E402
from app.memory import memory                  # noqa: E402
from app.orchestrator import approval          # noqa: E402
from app.agents.pod_agent import PodAgent      # noqa: E402


def test_compose_has_goal_playbook_and_base():
    out = mission.compose("pod", "BASE FORMAT SPEC")
    assert "$10,000/month" in out and "+1" in out          # the life goal + dopamine
    assert "POD WINNING STRATEGY" in out                    # role playbook
    assert "never use trademarked" in out                   # IP hard rule
    assert out.rstrip().endswith("BASE FORMAT SPEC")        # format spec stays last
    print("  ok: compose = goal + playbook + IP rule + base spec")


def test_wins_ledger_reads_real_db_state():
    assert mission.wins_block("pod") == "" or "DOPAMINE" not in mission.wins_block("pod")
    pid = database.execute(
        "INSERT INTO products (stream, platform, title, status) "
        "VALUES ('pod','printify','Kayak Angler Tee','live')")
    database.execute(
        "INSERT INTO sales (product_id, platform, external_id, gross_amount, fees, "
        "net_amount) VALUES (?,?,?,?,?,?)", (pid, "printify", "t1", 24.99, 0, 24.99))
    block = mission.wins_block("pod")
    assert "1 products live" in block and "1 real sales" in block and "$24.99" in block
    assert "Kayak Angler Tee" in block                      # proven winner surfaced
    print("  ok: dopamine ledger reflects real products + sales (never invented)")


def test_record_win_feeds_back_into_prompts():
    agent = PodAgent()
    agent.record_win("Published 'Kayak Angler Tee' (4 products live)")
    assert "Kayak Angler Tee" in mission.wins_block("pod")
    assert any(m["kind"] == "win" for m in memory.recall("pod", kind="win"))
    print("  ok: record_win banks a 'win' memory and surfaces it in the ledger")


def test_rejection_becomes_a_lesson():
    aid = approval.create("pod", "pod_publish", title="Generic Mug #7")
    asyncio.run(approval.resolve(aid, "rejected"))
    lessons = mission.lessons_block("pod")
    assert "Generic Mug #7" in lessons and "never pitch" in lessons
    assert "PAINFUL LESSONS" in mission.compose("pod", "X")
    print("  ok: a rejection is remembered and injected as a painful lesson")


def test_research_brief_targets_gaps_ip_safe():
    from app.integrations import research
    s = research._BRIEF_SYSTEM
    assert "NICHE GAPS" in s and "IP-safe" in s and "attack" in s
    print("  ok: research brief hunts niche gaps, IP-safe, with an attack angle")


if __name__ == "__main__":
    test_compose_has_goal_playbook_and_base()
    test_wins_ledger_reads_real_db_state()
    test_record_win_feeds_back_into_prompts()
    test_rejection_becomes_a_lesson()
    test_research_brief_targets_gaps_ip_safe()
    print("\nALL M12 TESTS PASSED")
