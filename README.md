# 🤖 AI Income Team

A local-first team of AI agents that build passive-income streams for you — a
print-on-demand store, digital products, and faceless videos — with a live
dashboard where you **see everything** and **approve every big decision**.

It runs entirely on **your own computer** using **free** APIs and tools. You keep
full control: nothing is published, posted, or spends money without your click.

> **Honest expectations:** this software builds the *machine* (products, listings,
> automation). It can't *guarantee* sales — real income depends on products and
> demand over time. Your revenue dashboard shows **real numbers only**, so it
> starts at a true **$0** and grows as real sales come in. Nothing is faked.

---

## What you need (all free, ~15 minutes, one time)

The in-app **Setup wizard** walks you through each of these and where to click:

1. **Google Gemini API key** — the agents' "brain". (aistudio.google.com)
2. **Groq API key** *(optional backup brain)*. (console.groq.com)
3. **Printify API token** — your print-on-demand store. (printify.com)
4. **Gumroad access token** — to sell digital products & track their sales. (gumroad.com)

You'll also connect your own **payout method** inside Printify so real earnings
reach you (only you can do that).

---

## How to start it

### The simple way — no terminal needed
1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/)
   (on Windows, tick **"Add Python to PATH"** during install). One time only.
2. Double-click the Start file for your system:
   - **Windows:** `Start.bat`
   - **macOS:** `Start.command`
   - **Linux:** `start.sh`

The first launch sets itself up automatically (it creates an isolated environment
and installs everything — this takes a few minutes once). Every launch after that
is instant. Your browser opens to the dashboard; set a PIN, then open **Settings**
to run the wizard. To stop it, close the little window that opened.

### Running from source (for developers)
```
pip install -r requirements.txt
python launcher.py
```
Your browser opens to `http://127.0.0.1:8765`.

### See it on your phone
The dashboard is mobile-friendly. When the app starts it creates a **secure link**
(via Cloudflare Tunnel) that works from anywhere — it appears on the Dashboard and
Settings pages. Your PIN protects it. On the same home wifi you can also use the
local link shown there. For the anywhere-link, the free `cloudflared` tool must be
installed (the Settings page tells you if it's missing).

---

## Your agent team

| Agent | What it does |
|-------|--------------|
| **Setup** | Guides one-time signups; stores keys securely. |
| **Print-on-Demand** | Designs products on Printify; waits for your approval to publish. |
| **Digital Products** | Writes a real PDF product + cover + listing copy; hands you a one-click flow to list it on Gumroad. |
| **Faceless Video** | Writes a script, voices it locally (Piper TTS), generates scenes, and assembles a captioned vertical MP4 (ffmpeg) ready to upload to YouTube. |
| **Marketing** | Drafts promo posts + graphics for your live products and hands you a prefilled X/Reddit/Facebook composer — you review and hit Post. |
| **Bookkeeper** | Pulls **real** sales data only; keeps revenue honest. |

Agents marked *(Milestone …)* are wired in but disabled — we build and switch them
on together, in order.

---

## Your control

- **Approvals:** publish/post/spend actions stop and wait for you on the Approvals page.
- **On/off + Run now:** toggle any agent or trigger it manually from the Dashboard.
- **Everything is logged:** the live feed shows every action as it happens.

## Privacy & safety

- API keys are stored **encrypted on your machine** (OS keychain when available),
  never in plain text and never sent anywhere except the service they belong to.
- The dashboard is protected by a **PIN** you set on first run.
- Never send personal/secret info through the AI brain — free-tier providers may use
  inputs to improve their models.
