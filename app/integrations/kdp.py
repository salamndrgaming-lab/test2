"""Amazon KDP handoff (no API).

KDP has no public API for creating titles, so this is a pure handoff: the KDP agent
builds a real print-ready interior PDF + a cover image + listing copy, then links you
to KDP's "create paperback" page where you upload them. The final cover/spine is
finished in KDP's free Cover Creator. KDP royalties are recorded via the honest
manual-revenue feature (copied from your KDP reports).
"""
from __future__ import annotations

DASHBOARD_URL = "https://kdp.amazon.com/"
CREATE_PAPERBACK_URL = "https://kdp.amazon.com/en_US/title-setup/paperback/new/details"
DEFAULT_TRIM = "6 x 9 in"
