"""JobRadar — FastAPI backend + scheduler. Serves the web UI and the JSON API."""
import asyncio
import datetime as dt
import socket
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Form, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import config, db, notify, sources

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Holds the result of the last refresh so the UI can show source health.
last_run = {"at": None, "new": 0, "report": {}}
_lock = asyncio.Lock()


async def run_refresh(notify_on_new: bool = True) -> dict:
    """Fetch everything, keep India/Bengaluru jobs in the shared pool, then
    email each user the new jobs that match THEIR saved role."""
    async with _lock:  # never overlap a manual refresh with the scheduled one
        # collect every role users want, so Adzuna can target them in Bengaluru
        roles = set()
        for u in db.all_users():
            for r in u["prefs"].get("roles", []):
                if r.strip():
                    roles.add(r.strip())
        raw, report = await sources.fetch_all(list(roles))

        # de-dup this batch, then apply the GLOBAL location rule (Bengaluru
        # on-site / India-eligible remote). Role filtering is per-user, later.
        seen, kept = set(), []
        for j in raw:
            if j["id"] in seen:
                continue
            seen.add(j["id"])
            if sources.passes_location(j):
                kept.append(j)

        now_iso = dt.datetime.now().isoformat(timespec="seconds")
        new_jobs = db.upsert_jobs(kept, now_iso)

        if new_jobs and notify_on_new:
            for user in db.all_users():
                prefs = user["prefs"]
                # only the brand-new jobs that match this user's role
                personal = sources.filter_for_user(
                    [dict(j) for j in new_jobs], prefs)
                if not personal:
                    continue
                if prefs.get("notify_email") and user["email"]:
                    notify.send_email(user["email"], personal)
                if prefs.get("notify_whatsapp") and prefs.get("whatsapp_phone") \
                        and prefs.get("whatsapp_apikey"):
                    notify.send_whatsapp(prefs["whatsapp_phone"],
                                         prefs["whatsapp_apikey"], personal)
            notify.desktop_notify(new_jobs)  # best-effort local popup

        last_run.update(at=now_iso, new=len(new_jobs), report=report,
                        kept=len(kept), fetched=len(raw))
        print(f"[refresh] fetched={len(raw)} kept(India)={len(kept)} new={len(new_jobs)}")
        return last_run


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    scheduler.add_job(
        run_refresh, "interval", minutes=config.REFRESH_MINUTES,
        id="refresh", next_run_time=dt.datetime.now() + dt.timedelta(seconds=2),
    )
    scheduler.start()
    _print_banner()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="JobRadar", lifespan=lifespan)

# Paths reachable without logging in.
PUBLIC_PATHS = {"/login", "/register", "/health", "/manifest.webmanifest",
                "/sw.js", "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png"}


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/web/"):
        return await call_next(request)
    if request.session.get("uid"):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return RedirectResponse("/login")


# Added AFTER auth_gate so SessionMiddleware wraps it (outermost) and
# request.session is populated before auth_gate reads it.
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY,
                   max_age=60 * 60 * 24 * 30, same_site="lax")


def current_user(request: Request) -> dict | None:
    uid = request.session.get("uid")
    return db.get_user_by_id(uid) if uid else None


def _auth_page(mode: str, err: str = "") -> str:
    """Render the login or register card (mode = 'login' | 'register')."""
    is_reg = mode == "register"
    err_html = f'<p class="text-sm text-red-400 text-center">{err}</p>' if err else ""
    extra = ""
    if is_reg:
        extra = """
        <input name=email type=email placeholder="Email (for job alerts)"
         class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 focus:outline-none focus:border-blue-500">
        <input name=role placeholder="Job role you want (e.g. python developer)"
         class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 focus:outline-none focus:border-blue-500">
        <input name=code placeholder="Invite code (if required)"
         class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 focus:outline-none focus:border-blue-500">"""
    action = "/register" if is_reg else "/login"
    title = "Create account" if is_reg else "Sign in"
    switch = ('Have an account? <a href="/login" class="text-blue-400">Sign in</a>'
              if is_reg else
              'New here? <a href="/register" class="text-blue-400">Create an account</a>')
    return f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>JobRadar — {title}</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-4">
<form method=post action={action} class="bg-slate-900 border border-slate-800 rounded-2xl p-6 w-full max-w-sm space-y-3">
<div class="text-center"><div class="text-4xl">🛰️</div><h1 class="font-bold text-xl mt-1">JobRadar</h1>
<p class="text-xs text-slate-400">{title}</p></div>
{err_html}
<input name=username placeholder=Username autofocus autocapitalize=none
 class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 focus:outline-none focus:border-blue-500">
<input name=password type=password placeholder=Password
 class="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 focus:outline-none focus:border-blue-500">
{extra}
<button class="w-full bg-blue-600 hover:bg-blue-500 rounded-lg py-2.5 font-medium">{title}</button>
<p class="text-xs text-slate-400 text-center">{switch}</p>
</form></body></html>"""


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return _auth_page("login")


@app.post("/login")
def login_submit(request: Request, username: str = Form(""), password: str = Form("")):
    user = db.verify_user(username, password)
    if user:
        request.session["uid"] = user["id"]
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(_auth_page("login", "Wrong username or password"), status_code=401)


@app.get("/register", response_class=HTMLResponse)
def register_page():
    return _auth_page("register")


@app.post("/register")
def register_submit(request: Request, username: str = Form(""), password: str = Form(""),
                    email: str = Form(""), role: str = Form(""), code: str = Form("")):
    if config.REGISTRATION_CODE and code.strip() != config.REGISTRATION_CODE:
        return HTMLResponse(_auth_page("register", "Invalid invite code"), status_code=403)
    if len(username.strip()) < 3 or len(password) < 6:
        return HTMLResponse(_auth_page("register",
            "Username needs 3+ chars and password 6+ chars"), status_code=400)
    user = db.create_user(username, password, email)
    if not user:
        return HTMLResponse(_auth_page("register", "That username is taken"), status_code=409)
    roles = [r.strip() for r in role.split(",") if r.strip()]
    if roles:
        db.update_prefs(user["id"], {"roles": roles})
    request.session["uid"] = user["id"]
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


@app.get("/health")
def health():
    return {"ok": True, "last_run": last_run.get("at")}


# ---------------------------------------------------------------- API ----
@app.get("/api/me")
def api_me(request: Request):
    u = current_user(request)
    return {"username": u["username"], "email": u["email"], "prefs": u["prefs"]}


@app.get("/api/jobs")
def api_jobs(request: Request, query: str = "", source: str = "",
             new_only: bool = False, saved_only: bool = False):
    u = current_user(request)
    rows = db._candidate_rows(u["id"], query, source)
    jobs = sources.filter_for_user(rows, u["prefs"], new_only, saved_only)
    return jobs[:500]


@app.get("/api/stats")
def api_stats(request: Request):
    u = current_user(request)
    rows = db._candidate_rows(u["id"])
    mine = sources.filter_for_user(rows, u["prefs"])
    sources_count: dict = {}
    for j in mine:
        sources_count[j["source"]] = sources_count.get(j["source"], 0) + 1
    return {
        "total": len(mine),
        "new": sum(1 for j in mine if j.get("is_new")),
        "saved": sum(1 for j in mine if j.get("saved")),
        "sources": [{"source": k, "c": v} for k, v in
                    sorted(sources_count.items(), key=lambda x: -x[1])],
        "last_run": last_run,
        "refresh_minutes": config.REFRESH_MINUTES,
    }


@app.post("/api/refresh")
async def api_refresh():
    return await run_refresh()


@app.post("/api/search-now")
async def api_search_now(request: Request):
    """Instant: pull THIS user's role(s) from Adzuna's Bengaluru search and store
    any new ones — no waiting for the 30-min cycle."""
    u = current_user(request)
    roles = u["prefs"].get("roles", [])
    jobs = await sources.search_adzuna_roles(roles)
    kept = [j for j in jobs if sources.passes_location(j)]
    now_iso = dt.datetime.now().isoformat(timespec="seconds")
    new = db.upsert_jobs(kept, now_iso)
    return {"searched": roles, "found": len(kept), "added": len(new)}


@app.post("/api/test-alert")
def api_test_alert(request: Request):
    """Send a sample alert through the user's enabled channels, right now, so they
    can confirm email/WhatsApp delivery works."""
    u = current_user(request)
    prefs = u["prefs"]
    sample = [{
        "title": "Test job — JobRadar is working ✅",
        "company": "JobRadar", "url": "http://localhost:8000",
        "location": "Bengaluru", "source": "Test",
    }]
    result = {"email": None, "whatsapp": None}
    if prefs.get("notify_email"):
        result["email"] = ("sent" if u["email"] and notify.send_email(u["email"], sample)
                           else "failed (check Gmail SMTP in .env and your email in Settings)")
    if prefs.get("notify_whatsapp"):
        ok = (prefs.get("whatsapp_phone") and prefs.get("whatsapp_apikey")
              and notify.send_whatsapp(prefs["whatsapp_phone"], prefs["whatsapp_apikey"], sample))
        result["whatsapp"] = "sent" if ok else "failed (check number + CallMeBot key in Settings)"
    return result


@app.post("/api/seen")
def api_seen(request: Request):
    db.mark_seen(current_user(request)["id"])
    return {"ok": True}


@app.post("/api/jobs/{job_id}/{action}")
def api_action(request: Request, job_id: str, action: str):
    mapping = {"save": ("saved", 1), "unsave": ("saved", 0),
               "dismiss": ("dismissed", 1)}
    if action not in mapping:
        return JSONResponse({"error": "unknown action"}, status_code=400)
    field, value = mapping[action]
    db.set_user_job_flag(current_user(request)["id"], job_id, field, value)
    return {"ok": True}


@app.get("/api/settings")
def api_get_settings(request: Request):
    u = current_user(request)
    return {**u["prefs"], "email": u["email"]}


@app.post("/api/settings")
def api_set_settings(request: Request, payload: dict):
    u = current_user(request)
    if "email" in payload:
        db.update_email(u["id"], payload.pop("email") or "")
    return db.update_prefs(u["id"], payload)


# ------------------------------------------------------------- web UI ----
@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


# PWA assets served from the site root (service workers need root scope).
@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(WEB_DIR / "manifest.webmanifest",
                        media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    # Served from root so the SW can control the whole app.
    return FileResponse(WEB_DIR / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/icon-192.png")
def icon192():
    return FileResponse(WEB_DIR / "icon-192.png")


@app.get("/icon-512.png")
def icon512():
    return FileResponse(WEB_DIR / "icon-512.png")


@app.get("/apple-touch-icon.png")
def apple_icon():
    return FileResponse(WEB_DIR / "icon-192.png")


app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")


# ------------------------------------------------------------- runtime ---
def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:  # noqa: BLE001
        return "127.0.0.1"


def _print_banner():
    ip = _lan_ip()
    print("\n" + "=" * 56)
    print("  🛰️  JobRadar is running")
    print("  On this computer : http://localhost:%d" % config.PORT)
    print("  On your phone     : http://%s:%d" % (ip, config.PORT))
    print("  (phone must be on the same Wi-Fi)")
    print("=" * 56 + "\n")


def main():
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)


if __name__ == "__main__":
    main()
