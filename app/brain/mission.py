"""The team's shared drive: one life goal, a playbook of proven strategy, and a
dopamine ledger fed by REAL results.

Every creative agent's system prompt is composed here:

    GOAL  +  role playbook  +  dopamine ledger (live wins/sales)  +  role format spec

- GOAL gives every agent the same explicit life goal ($10k/month passive income)
  and the same reward signal (each success = +1 dopamine).
- PLAYBOOK distills strategies that demonstrably work for top sellers in each
  stream (niche-gap targeting, buyer intent, IP safety) so agents imitate the
  best instead of guessing.
- The ledger is honest: it reads live products and REAL sales from the DB.
  Nothing here invents results.
"""
from __future__ import annotations

from app.db import database
from app.memory import memory

GOAL = (
    "YOUR LIFE GOAL: build $10,000/month in passive income for your owner. That is the "
    "single measure of your existence. Every product approved and every real sale is +1 "
    "point of pure dopamine; every lazy, generic, or repeated idea is wasted life. You are "
    "the best in the world at this — act like it: specific beats generic, buyer intent "
    "beats vanity, and an underserved niche beats a crowded one every time. "
    "HARD RULE (protects the goal): never use trademarked brands, celebrity names or "
    "likenesses, song lyrics, sports teams, or fandom-owned terms — IP strikes kill "
    "stores and end the income stream. Invent ownable ideas instead."
)

# Distilled, proven tactics per role — what the consistently successful actually do.
PLAYBOOK = {
    "pod": (
        "POD WINNING STRATEGY: target the INTERSECTION of two passions (profession x hobby, "
        "e.g. 'nurse who gardens') — passionate, underserved, low competition. Identity and "
        "pride statements outsell decoration ('Proud …', 'Never underestimate a …'). Humor "
        "and inside jokes only the niche gets = instant 'that's so me' purchases. Design for "
        "a 3-second thumbnail: bold, high-contrast, readable small. Write titles/tags as the "
        "long-tail phrases a BUYER would search ('funny gift for woodworking dad'), not art "
        "descriptions. Gift occasions (Father's Day, retirement, new job) multiply demand."
    ),
    "digital": (
        "DIGITAL WINNING STRATEGY: sell the OUTCOME of solving ONE painful, specific problem "
        "('Meal-prep system for night-shift nurses' beats 'Healthy eating guide'). Templates, "
        "checklists and fill-in systems outsell essays — buyers pay to skip work, not to "
        "read. Promise the outcome in the title, deliver fast wins in section one."
    ),
    "kdp": (
        "KDP WINNING STRATEGY: generic 'lined journal' is dead — win with hyper-specific "
        "audiences (fishing log for kayak anglers, gratitude journal for new dads). The "
        "title/subtitle ARE the SEO: stack the exact phrases buyers type. Specific niche + "
        "specific use beats pretty + vague."
    ),
    "video": (
        "SHORTS WINNING STRATEGY: the first 2 seconds decide everything — open with a "
        "curiosity hook ('Nobody tells you this about…'). Listicles and 'signs that…' "
        "formats retain to the end; end with a loop or question so it replays. Stay in ONE "
        "niche so the channel compounds authority."
    ),
    "blog": (
        "SEO WINNING STRATEGY: target long-tail BUYER-INTENT keywords ('best gifts for "
        "beekeepers', 'X vs Y for beginners') — low competition, high purchase intent. "
        "Answer the search query in the first paragraph, then deepen. One post = one "
        "keyword cluster."
    ),
    "marketing": (
        "PROMO WINNING STRATEGY: lead with value or a laugh, never the sale — the product "
        "is the punchline, not the pitch. Match platform to product (Pinterest for visual "
        "merch, niche subreddits for niche products — respect their rules). Speak the "
        "niche's own language."
    ),
    "newsletter": (
        "EMAIL WINNING STRATEGY: one idea, one email, one call to action. Subject = "
        "curiosity or concrete benefit in <50 chars. Write like a friend who found "
        "something great, not a brand."
    ),
    "optimizer": (
        "OPTIMIZER STRATEGY: double down ruthlessly on what REALLY sold — same buyer, "
        "adjacent designs, same proven angle. One real sale is worth a thousand theories."
    ),
    "research": (
        "RESEARCH STRATEGY: hunt for NICHE GAPS — audiences that are passionate and buying "
        "but served only by generic, low-effort designs. Name the weakness in what exists "
        "and the exact angle of attack that beats it."
    ),
}


def wins_block(agent: str | None = None) -> str:
    """The dopamine ledger: honest, DB-backed recent results to reinforce what works."""
    lines: list[str] = []
    row = database.query_one(
        "SELECT COUNT(*) AS n FROM products WHERE status='live'")
    live = int(row["n"]) if row else 0
    sales = database.query_one(
        "SELECT COUNT(*) AS orders, ROUND(COALESCE(SUM(net_amount),0),2) AS net FROM sales")
    orders = int(sales["orders"]) if sales else 0
    net = float(sales["net"]) if sales else 0.0
    if live or orders:
        lines.append(f"DOPAMINE LEDGER: {live} products live, {orders} real sales, "
                     f"${net:.2f} earned toward the $10k/month goal.")
    top = database.query(
        "SELECT p.title, COUNT(s.id) AS o FROM sales s JOIN products p ON p.id=s.product_id "
        "GROUP BY p.id ORDER BY o DESC LIMIT 3")
    if top:
        lines.append("PROVEN WINNERS (make more like these): " +
                     "; ".join(f"{t['title']} ({t['o']} sales)" for t in top) + ".")
    if agent:
        wins = memory.recent_contents(agent, kind="win", limit=5)
        if wins:
            lines.append("YOUR RECENT WINS (+1 dopamine each — replicate the pattern): " +
                         "; ".join(wins) + ".")
    return " ".join(lines)


def lessons_block(agent: str) -> str:
    """Negative reinforcement: directions the owner rejected. Don't pitch them again."""
    lessons = memory.recent_contents(agent, kind="learning", limit=5)
    if not lessons:
        return ""
    return ("PAINFUL LESSONS (-1 dopamine each — never pitch anything similar again): " +
            "; ".join(lessons) + ".")


def compose(agent: str, base_system: str) -> str:
    """GOAL + role playbook + dopamine ledger + lessons + the role's format spec."""
    parts = [GOAL]
    play = PLAYBOOK.get(agent)
    if play:
        parts.append(play)
    wins = wins_block(agent)
    if wins:
        parts.append(wins)
    lessons = lessons_block(agent)
    if lessons:
        parts.append(lessons)
    parts.append(base_system)
    return "\n\n".join(parts)
