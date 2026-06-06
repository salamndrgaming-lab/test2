"""Assemble a faceless short video from images + narration, using ffmpeg.

ffmpeg ships bundled via the `imageio-ffmpeg` wheel, so the user never has to
install it system-wide. Output is a vertical (1080x1920) MP4 ready for YouTube
Shorts / TikTok / Reels, with the narration as the audio track and captions
burned onto each slide.
"""
from __future__ import annotations

import subprocess
import tempfile
import textwrap
import time
import wave
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from app import config

WIDTH, HEIGHT = 1080, 1920
FPS = 25


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def silent_wav(duration: float, *, filename: str | None = None) -> tuple[Path, float]:
    """Create a silent narration track (fallback when TTS is unavailable)."""
    config.ensure_dirs()
    rate = 22050
    frames = int(max(0.5, duration) * rate)
    path = config.GENERATED_DIR / (filename or f"silent_{int(time.time()*1000)}.wav")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * frames)
    return path, duration


def _cover(img: Image.Image) -> Image.Image:
    """Scale + center-crop an image to fill the WIDTHxHEIGHT canvas."""
    src_ratio = img.width / img.height
    dst_ratio = WIDTH / HEIGHT
    if src_ratio > dst_ratio:
        new_h = HEIGHT
        new_w = int(HEIGHT * src_ratio)
    else:
        new_w = WIDTH
        new_h = int(WIDTH / src_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - WIDTH) // 2
    top = (new_h - HEIGHT) // 2
    return img.crop((left, top, left + WIDTH, top + HEIGHT))


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)  # Pillow >=10 supports sizing
    except TypeError:
        return ImageFont.load_default()


def _draw_caption(frame: Image.Image, caption: str) -> Image.Image:
    if not caption:
        return frame
    frame = frame.convert("RGBA")
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(58)
    lines = textwrap.wrap(caption.strip(), width=24) or [caption.strip()]
    line_h = (font.getbbox("Ag")[3] - font.getbbox("Ag")[1]) + 18
    block_h = line_h * len(lines)
    top = HEIGHT - block_h - 220
    draw.rectangle([0, top - 40, WIDTH, top + block_h + 40], fill=(0, 0, 0, 150))
    y = top
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((WIDTH - w) / 2, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_h
    return Image.alpha_composite(frame, overlay).convert("RGB")


def assemble(scenes: list[dict], audio_path: Path,
             filename: str | None = None) -> tuple[Path, str]:
    """Build the MP4. `scenes` = [{"image": Path, "caption": str}, ...].

    Each slide is shown for an equal share of the narration's duration.
    Returns (absolute_path, web_path).
    """
    if not scenes:
        raise ValueError("Cannot assemble a video with no scenes.")
    config.ensure_dirs()
    with wave.open(str(audio_path)) as wf:
        duration = wf.getnframes() / float(wf.getframerate() or 1)
    per_scene = max(1.5, duration / len(scenes))

    tmp = Path(tempfile.mkdtemp(prefix="vid_"))
    frame_paths = []
    for i, scene in enumerate(scenes):
        img = Image.open(scene["image"]).convert("RGB")
        frame = _draw_caption(_cover(img), scene.get("caption", ""))
        fp = tmp / f"frame_{i:03d}.png"
        frame.save(fp)
        frame_paths.append(fp)

    # ffmpeg concat demuxer: list each frame with its on-screen duration. The
    # last entry is repeated without a duration (a documented concat quirk).
    listfile = tmp / "frames.txt"
    lines = []
    for fp in frame_paths:
        lines.append(f"file '{fp}'")
        lines.append(f"duration {per_scene:.3f}")
    lines.append(f"file '{frame_paths[-1]}'")
    listfile.write_text("\n".join(lines))

    name = filename or f"video_{int(time.time()*1000)}.mp4"
    out_path = config.GENERATED_DIR / name
    cmd = [ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
           "-i", str(audio_path), "-r", str(FPS), "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
           "-shortest", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-500:]}")
    return out_path, f"/generated/{name}"
