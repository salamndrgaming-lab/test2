"""Keyless, offline image generation — the always-works fallback.

When every online image generator is unavailable (no token, rate-limited, or
down), we still need *an* image so POD/video/marketing never hard-fail. This
renders a clean typographic design locally with Pillow (already a dependency):
the product's phrase, wrapped and centred on a tasteful background, with an
accent bar. For apparel/stickers we render on a transparent background (real
"text merch"); for video scenes we render on a gradient so captions read.

No network, no API key, deterministic look per phrase. Mirrors the font/wrap
handling already used for video captions in app/integrations/video.py.
"""
from __future__ import annotations

import hashlib
import io

from PIL import Image, ImageDraw, ImageFont

# (background_top, background_bottom, text, accent) — picked deterministically per phrase.
_PALETTES = [
    ((26, 34, 48), (14, 19, 26), (236, 240, 245), (63, 185, 80)),
    ((40, 22, 54), (20, 12, 28), (245, 238, 250), (188, 140, 255)),
    ((18, 38, 52), (10, 20, 28), (235, 245, 250), (88, 166, 255)),
    ((54, 32, 18), (28, 16, 10), (250, 240, 232), (210, 153, 34)),
    ((20, 48, 40), (10, 24, 20), (236, 248, 244), (45, 200, 150)),
    ((48, 20, 28), (26, 10, 14), (250, 236, 240), (248, 81, 73)),
]


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)  # Pillow >=10 supports sizing
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: float) -> list[str]:
    """Greedy word-wrap so each line fits within max_w pixels."""
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if not cur or draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [text]


def render_text_design(text: str, *, width: int, height: int,
                       transparent: bool = True) -> bytes:
    """Render a typographic design and return PNG bytes. Never makes a network call."""
    text = (text or "Design").strip()[:120]
    bg_top, bg_bot, fg, accent = _PALETTES[
        int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % len(_PALETTES)]

    if transparent:
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    else:
        # Vertical gradient background.
        col = Image.new("RGB", (1, height))
        for y in range(height):
            t = y / max(1, height - 1)
            col.putpixel((0, y), tuple(int(bg_top[i] + (bg_bot[i] - bg_top[i]) * t)
                                       for i in range(3)))
        img = col.resize((width, height)).convert("RGBA")

    draw = ImageDraw.Draw(img)
    margin = int(width * 0.1)
    max_w = width - 2 * margin

    # Shrink the font until the wrapped block fits the canvas.
    size = max(18, width // 8)
    while size > 14:
        font = _font(size)
        lines = _wrap(draw, text, font, max_w)
        line_h = (font.getbbox("Ag")[3] - font.getbbox("Ag")[1]) + int(size * 0.35)
        if line_h * len(lines) <= height - 2 * margin and \
                all(draw.textlength(ln, font=font) <= max_w for ln in lines):
            break
        size -= 4
    font = _font(size)
    lines = _wrap(draw, text, font, max_w)
    line_h = (font.getbbox("Ag")[3] - font.getbbox("Ag")[1]) + int(size * 0.35)

    y = (height - line_h * len(lines)) // 2
    text_color = accent if transparent else fg
    for line in lines:
        x = (width - draw.textlength(line, font=font)) / 2
        if not transparent:
            draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))  # subtle shadow
        draw.text((x, y), line, font=font, fill=text_color)
        y += line_h

    # Accent underline bar beneath the text block.
    bar_w = int(width * 0.3)
    bar_x = (width - bar_w) // 2
    bar_y = y + int(size * 0.2)
    if bar_y < height - margin // 2:
        draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + max(4, size // 12)], fill=accent)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
