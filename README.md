# 🛰️ JobRadar

A tiny, self-hosted **job aggregator** that pulls listings from multiple free job
boards. Each person **logs in, saves the job role they want**, and sees **only**
jobs whose title matches that role — located in **Bengaluru (on-site)** or
**remote roles open to India**. It flags **new** postings and **emails** each
user their matches. Clean **web UI** you can open on your PC, Mac, or **phone**
(installable as an app) — no paid services, no database server.

> **Why not LinkedIn / "all websites"?** LinkedIn's Terms of Service prohibit
> scraping and they actively block it (risking IP/account bans). Instead,
> JobRadar uses official, free job-board APIs that legally aggregate huge numbers
> of postings — many originally sourced from LinkedIn, company sites, etc. This is
> reliable and won't break or get you banned. You can add more sources anytime.

## What it does
- Pulls jobs from **Remotive, RemoteOK, Arbeitnow, Jobicy, The Muse, Himalayas,
  WeWorkRemotely**, and optionally **Adzuna** (free key — the main source of
  Bengaluru *on-site* listings, incl. niche roles like game dev).
- > Note: **Naukri, Indeed, LinkedIn, Foundit/Monster, Instahyre** have no free
  > public API and their terms forbid scraping (you'd get blocked/banned), so
  > they're intentionally not included. Adzuna legally aggregates many India
  > postings instead.
- **Per-user accounts**: register, save your **role** (e.g. `python developer`),
  and see only matching jobs. Strict — every word of the role must be in the title.
- **Location locked to your rule**: on-site → Bengaluru only; remote → India-eligible
  (India / Worldwide / Anywhere / Asia / APAC) only.
- Auto-checks every 30 min and **emails each user** their new matching jobs.
- **Web dashboard**: search, filter by source / new / saved, save or hide jobs.
- Stores everything in a single local `jobradar.db` (SQLite) — zero setup.

---

## Quick start

### Windows
Double-click **`start.bat`** (or run it in a terminal). That's it.

### macOS / Linux
```bash
chmod +x start.sh
./start.sh
```

The first run creates a virtual environment and installs dependencies
automatically. When it's ready you'll see:

```
🛰️  JobRadar is running
  On this computer : http://localhost:8000
  On your phone     : http://192.168.x.x:8000
```

Open the first URL in your browser. To use it on your **phone**, make sure the
phone is on the **same Wi-Fi** and open the second URL.

> Manual run (if you prefer): `pip install -r requirements.txt` then `python -m app.main`

---

## Configuration (all optional)

Copy `.env.example` to `.env` and edit. Your **role**, **email**, and alert
toggle are set per-account from the **⚙️ Settings** button after you log in.

### First run
Open the app → **Create an account** (username + password) → set your **role**
and **email**. Each person who registers gets their own role-filtered feed.

### Email notifications (Gmail example)
1. Turn on 2-Step Verification, then create an **App Password**:
   https://myaccount.google.com/apppasswords
2. In `.env` set `SMTP_USER`, `SMTP_PASS` (the app password) and `EMAIL_FROM`.
   This is just the *sending* account — each user receives alerts at the email
   in their own profile.

### WhatsApp alerts (free, via CallMeBot)
Per-user, set in **⚙️ Settings** — no server config needed. One-time setup:
1. Save the CallMeBot number to your contacts and WhatsApp it the exact text
   **“I allow callmebot to send me messages”**. The current number + steps are at
   https://www.callmebot.com/blog/free-api-whatsapp-messages/ (it occasionally
   changes; the app shows the number that was current at build time).
2. CallMeBot replies with your **API key**.
3. In JobRadar → ⚙️ Settings, tick **WhatsApp me**, enter your number (with country
   code, e.g. `+9198XXXXXXXX`) and the API key. Save.
   > Note: CallMeBot is for personal use (sends to your own number) and is
   > rate-limited — fine for job digests, not bulk messaging.

### Adzuna — get real Bengaluru on-site jobs (recommended!)
Without this you'll mostly see India-eligible *remote* roles. Adzuna is the main
source of **Bengaluru on-site** listings, and it's free:
1. Get a free key (1 min): https://developer.adzuna.com/
2. Put `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` in `.env`.

---

---

## 📱 Use it from ANYWHERE (deploy free + install on your phone)

This makes JobRadar reachable on the internet from any phone, anywhere — and
installable as an app on your home screen. We use **Render's free plan** (no
credit card) and a **free uptime pinger** so it keeps checking jobs and emailing
you 24/7.

### Step 1 — Put the code on GitHub
Create a new repo and push this folder (or upload the files via GitHub's web UI).

### Step 2 — Deploy on Render (free)
1. Sign up at https://render.com (free, no card).
2. Click **New + → Blueprint**, connect your repo. Render reads `render.yaml`
   and creates the service automatically.
3. When prompted, set the environment variables:
   - **`REGISTRATION_CODE`** (optional) — an invite code so only people you share
     it with can create an account. Leave blank for open signup.
   - **Email** (optional): `SMTP_USER`, `SMTP_PASS` (Gmail app password), `EMAIL_FROM`.
   - **`ADZUNA_APP_ID` / `ADZUNA_APP_KEY`** (recommended, for Bengaluru jobs).
   - `SECRET_KEY` is generated for you.
4. Click **Apply / Deploy**. In ~2–3 min you get a public URL like
   `https://jobradar-xxxx.onrender.com`.

> Prefer not to use a Blueprint? Use **New + → Web Service → Docker**, point it at
> the repo, and add the same env vars manually. Render auto-detects the `Dockerfile`.

### Step 3 — Keep it awake 24/7 (so alerts keep coming) — free
Render's free service "sleeps" after 15 min idle, which pauses the job checks.
Keep it awake with a free pinger:
1. Go to https://cron-job.org (free), create an account.
2. Add a cronjob that does a **GET** request to
   `https://YOUR-APP.onrender.com/health` every **10 minutes**.

That's it — it now wakes itself, checks all sources on schedule, and emails you
new jobs even while your phone/PC is off.

### Step 4 — Install it on your phone
Open your Render URL on your phone, create your account / log in, then:
- **Android (Chrome):** menu **⋮ → Add to Home screen / Install app**.
- **iPhone (Safari):** **Share → Add to Home Screen**.

It now opens full-screen like a native app, with the 🛰️ icon.

> ⚠️ Because it's public, set a **`REGISTRATION_CODE`** so strangers can't create
> accounts. Every page is already locked behind login.
>
> ℹ️ On Render's free plan storage is temporary, so on a redeploy/restart your
> **accounts** and *saved/hidden* flags reset — the job feed itself just
> re-populates on the next check. For permanent storage, attach a paid Render
> disk (set `JOBRADAR_DB` onto it) or use the always-on VPS option below.

---

## Other ways to run 24/7
- **Tunnel from your PC (free):** keep `start.bat`/`start.sh` running and expose it
  with `cloudflared tunnel --url http://localhost:8000`. Works only while your PC is on.
- **Cheap VPS (~$4–5/mo):** any small Linux server. Clone the repo, set env vars,
  run with Docker: `docker build -t jobradar . && docker run -p 80:8000 --env-file .env jobradar`.
- **Local only:** leave the terminal open (Mac: `nohup ./start.sh &`; Windows:
  Task Scheduler at login).

---

## Cost
**$0.** Everything used is free: free APIs, free libraries, local storage.
Only your electricity / an optional cheap VM if you want 24/7 cloud hosting.

## Add more job sources
Open `app/sources.py`, write a `fetch_yoursource(client)` coroutine that returns
normalized jobs via the `_mk(...)` helper, and add it to the `FETCHERS` list.

## Project layout
```
job-radar/
├── app/
│   ├── main.py      # FastAPI server + scheduler + API
│   ├── sources.py   # job-board fetchers + filtering
│   ├── db.py        # SQLite storage
│   ├── notify.py    # email + desktop notifications
│   └── config.py    # settings / .env loading
├── web/
│   ├── index.html          # the dashboard UI (also a PWA)
│   ├── manifest.webmanifest, sw.js, icon-*.png   # installable-app assets
├── tools/gen_icons.py      # regenerates the app icons (stdlib only)
├── Dockerfile, render.yaml # one-click free deploy to Render
├── start.bat / start.sh
├── requirements.txt
└── .env.example
```
