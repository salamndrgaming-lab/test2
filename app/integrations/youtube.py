"""YouTube publishing — handoff approach.

We deliberately do NOT auto-upload via the YouTube Data API. Two hard limits make
API upload a poor fit for a beginner running this themselves:
  • An unverified API app can only upload videos locked to PRIVATE, and they stay
    that way until Google audits the app.
  • Each upload costs ~1600 quota units against a 10,000/day cap (~6 videos/day).
Instead the agent produces the finished MP4 + title/description/tags and hands you
a one-click link to upload it yourself — no audit, no quota ceiling, you choose the
visibility. (Ad revenue has no beginner-friendly read API, so video earnings are
logged manually rather than auto-reconciled.)
"""
from __future__ import annotations

UPLOAD_URL = "https://www.youtube.com/upload"

QUOTA_WARNING = (
    "Tip: upload this manually via the link — the YouTube API would force the "
    "video to stay private and cap you at ~6 uploads/day."
)
