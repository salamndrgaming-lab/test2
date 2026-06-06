"""Generate a real, downloadable PDF product from structured content.

Used by the Digital Products agent to turn brain-written content into an actual
ebook/guide/checklist the user can sell. Pure-Python (reportlab) so it works
offline on any machine.
"""
from __future__ import annotations

import time
from pathlib import Path

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer)

from app import config


def _styles():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(name="CoverTitle", parent=base["Title"],
                            fontSize=30, leading=36, spaceAfter=24, alignment=TA_CENTER))
    base.add(ParagraphStyle(name="CoverSub", parent=base["Normal"],
                            fontSize=14, leading=20, alignment=TA_CENTER, textColor="#555555"))
    base.add(ParagraphStyle(name="H", parent=base["Heading1"], fontSize=18,
                            leading=22, spaceBefore=18, spaceAfter=10))
    base.add(ParagraphStyle(name="Body2", parent=base["BodyText"], fontSize=11.5,
                            leading=17, spaceAfter=8))
    return base


def generate_pdf(title: str, subtitle: str, sections: list[dict],
                 filename: str | None = None) -> tuple[Path, str]:
    """Build a multi-page PDF. `sections` = [{"heading": str, "body": str}, ...].

    Returns (absolute_path, web_path) where web_path is served at /generated/...
    """
    config.ensure_dirs()
    name = filename or f"product_{int(time.time()*1000)}.pdf"
    out_path = config.GENERATED_DIR / name

    styles = _styles()
    doc = SimpleDocTemplate(str(out_path), pagesize=LETTER,
                            topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                            leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            title=title)
    flow = [Spacer(1, 2.2 * inch),
            Paragraph(title, styles["CoverTitle"])]
    if subtitle:
        flow.append(Paragraph(subtitle, styles["CoverSub"]))
    flow.append(PageBreak())

    for sec in sections:
        heading = (sec.get("heading") or "").strip()
        body = (sec.get("body") or "").strip()
        if heading:
            flow.append(Paragraph(heading, styles["H"]))
        for para in [p for p in body.split("\n") if p.strip()]:
            flow.append(Paragraph(para.strip().replace("&", "&amp;"), styles["Body2"]))
        flow.append(Spacer(1, 6))

    doc.build(flow)
    return out_path, f"/generated/{name}"
