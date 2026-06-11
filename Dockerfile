# AI Income Team — full engine container (runs everything 24/7).
# Works on any container host (Render, Railway, Fly.io). NOT for Vercel — this app
# needs a long-running process (background scheduler + WebSockets), a persistent disk
# (SQLite + encrypted vault + generated files), and ffmpeg, none of which fit Vercel's
# serverless model. See DEPLOY.md.
FROM python:3.12-slim

# System deps: ffmpeg (video assembly), espeak-ng + libgomp1 (Piper TTS / onnxruntime).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg espeak-ng libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AIT_HOST=0.0.0.0 \
    AIT_NO_TUNNEL=1 \
    AIT_DATA_DIR=/data \
    IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

# Persistent data (DB, vault, generated files) lives here — mount a volume at /data.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8765
# Bind to the platform-provided $PORT (Render/Railway set it); default 8765 locally.
# --proxy-headers makes wss:// + redirects work behind the host's TLS proxy.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8765} --proxy-headers --forwarded-allow-ips='*'"]
