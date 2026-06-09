"""Export published blog posts to static HTML for free hosting (Netlify / GitHub Pages).

Writes a self-contained folder (index + one page per post + sitemap.xml) into the data
directory. The user drags that folder onto Netlify Drop or commits it to GitHub Pages —
no credentials, no paid service. This turns the blog into permanent, public, SEO-able
pages that drive organic traffic even when the local app is off.
"""
from __future__ import annotations

import html
from pathlib import Path

from app import config
from app.db import database


def _page(title: str, inner: str) -> str:
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;"
        "padding:0 1rem;line-height:1.6;color:#1a1a1a}h1,h2{line-height:1.25}"
        ".cta{background:#f3f4f6;padding:1rem;border-radius:8px}a{color:#2563eb}</style>"
        f"</head><body>{inner}</body></html>")


def export() -> tuple[Path, int]:
    out = config.DATA_DIR / "blog_export"
    out.mkdir(parents=True, exist_ok=True)
    posts = database.query(
        "SELECT * FROM blog_posts WHERE status='published' "
        "ORDER BY published_at DESC, id DESC")

    items = "".join(
        f'<li><a href="{p["slug"]}.html">{html.escape(p["title"])}</a>'
        f"<p>{html.escape(p.get('summary') or '')}</p></li>" for p in posts)
    (out / "index.html").write_text(
        _page("Blog", f"<h1>Blog</h1><ul>{items}</ul>"), encoding="utf-8")

    for p in posts:
        inner = ('<p><a href="index.html">← All posts</a></p>'
                 f"<h1>{html.escape(p['title'])}</h1>{p.get('body_html') or ''}")
        (out / f"{p['slug']}.html").write_text(_page(p["title"], inner), encoding="utf-8")

    urls = "".join(f"<url><loc>{p['slug']}.html</loc></url>" for p in posts)
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>", encoding="utf-8")
    return out, len(posts)
