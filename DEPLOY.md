# Running AI Income Team online

You have two independent pieces:

1. **The engine** (dashboard + agents + Vault + revenue) → a **container host** that runs
   24/7. Vercel cannot run this part (it needs a long-running process, WebSockets, a
   persistent disk, and ffmpeg — none of which fit Vercel's serverless model).
2. **The public blog** (for free SEO traffic) → **Vercel** (static, free).

You can run #1 on your own PC (double-click Start) and still publish #2 to Vercel. Or run
both in the cloud, below.

---

## 1) The engine → Render (recommended), Railway, or Fly.io

The repo ships a `Dockerfile` and `render.yaml`, so any container host works. **Render** is
the most click-friendly.

### Render (uses `render.yaml`)
1. Push this repo to GitHub (already done if you're reading this there).
2. Go to **render.com → New → Blueprint**, pick this repo. Render reads `render.yaml`.
3. It creates a web service on the **Starter** plan with a **1 GB persistent disk** at
   `/data` (holds your database, encrypted vault, and generated files). The disk needs a
   paid instance — about **$7/month**. (Render's free tier has no disk and sleeps, so
   state would be lost — not suitable here.)
4. Open the service URL, **set a strong PIN**, then **Settings** to add your API keys.

### Railway / Fly.io (alternatives)
- **Railway:** New Project → Deploy from Repo (it uses the `Dockerfile`). Add a **Volume**
  mounted at `/data`. Set env `AIT_DATA_DIR=/data`, `AIT_HOST=0.0.0.0`, `AIT_NO_TUNNEL=1`.
- **Fly.io:** `fly launch` (detects the `Dockerfile`), then `fly volumes create ait_data
  --size 1` and mount it at `/data` in `fly.toml`. Same env vars.

### What the container does
- Binds to the host's `$PORT`, no Cloudflare tunnel (`AIT_NO_TUNNEL=1` — the host already
  gives you a public HTTPS URL). WebSockets/Vault/scheduler/ffmpeg all work.
- All state lives on the mounted volume at `/data`, so it survives restarts/redeploys.

### Honest trade-offs of cloud-hosting the engine
- **Your API keys live on the host** (encrypted on the volume), not just your machine.
- Running 24/7 means agents keep proposing work — **check the Approvals page** regularly.
- A persistent host costs **a few dollars a month** (true $0 only on your own PC).
- The public URL is protected **only by your PIN** — use a strong one.

---

## 2) The public blog → Vercel (free, static)

The blog is served two ways: live at `/blog` on the engine, and as **static HTML** you can
host free on Vercel for permanent, fast, SEO-able pages (works even when the engine is off).

### Deploy
The repo's root `vercel.json` makes Vercel deploy the static site in **`vercel-blog/`**
(no build step). Two options:
- **Dashboard:** vercel.com → New Project → import this repo → Deploy.
- **CLI:** `npx vercel --prod` from the repo root.

### Keep it updated as you publish posts
1. In the app, approve blog posts (SEO Blog agent), then call **Export** (Dashboard/Blog or
   `POST /api/blog/export`). This writes `data/blog_export/` (HTML + `sitemap.xml` +
   `vercel.json`).
2. Deploy that folder: `npx vercel deploy data/blog_export --prod` — or copy its contents
   into `vercel-blog/` and redeploy from the repo.

That's it: the engine runs everything online on a container host, and your public blog lives
on Vercel for free.
