"""Job sources. Each fetcher hits a free, public job-board API and returns a
list of normalized dicts. All are wrapped so one failing source never breaks
the rest. Add new sources by writing a fetch_* coroutine and listing it below.
"""
import datetime as dt
import hashlib
import html
import re
import xml.etree.ElementTree as ET

import httpx

from . import config

UA = {"User-Agent": "JobRadar/1.0 (personal job aggregator)"}
TIMEOUT = httpx.Timeout(25.0)

REMOTE_HINTS = ("remote", "anywhere", "work from home", "wfh", "distributed")


def _clean(text: str | None, limit: int = 600) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)          # strip HTML tags
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _is_remote(*fields: str) -> bool:
    blob = " ".join(f.lower() for f in fields if f)
    return any(h in blob for h in REMOTE_HINTS)


def _mk(source, title, company, location, url, description, posted_at, remote=None):
    title = (title or "").strip() or "Untitled role"
    company = (company or "").strip() or "Unknown"
    location = (location or "").strip()
    if remote is None:
        remote = _is_remote(location, title)
    job_id = hashlib.sha1(f"{source}|{url}".encode()).hexdigest()
    return {
        "id": job_id,
        "title": title,
        "company": company,
        "location": location or ("Remote" if remote else ""),
        "remote": bool(remote),
        "url": url or "",
        "source": source,
        "description": _clean(description),
        "posted_at": (posted_at or "")[:25],
    }


async def fetch_remotive(client) -> list[dict]:
    r = await client.get("https://remotive.com/api/remote-jobs", headers=UA)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append(_mk(
            "Remotive", j.get("title"), j.get("company_name"),
            j.get("candidate_required_location"), j.get("url"),
            j.get("description"), j.get("publication_date"), remote=True,
        ))
    return out


async def fetch_remoteok(client) -> list[dict]:
    r = await client.get("https://remoteok.com/api", headers=UA)
    r.raise_for_status()
    out = []
    for j in r.json():
        if not isinstance(j, dict) or "id" not in j:  # first item is a legal notice
            continue
        out.append(_mk(
            "RemoteOK", j.get("position") or j.get("title"), j.get("company"),
            j.get("location"), j.get("url"),
            j.get("description"), j.get("date"), remote=True,
        ))
    return out


async def fetch_arbeitnow(client) -> list[dict]:
    r = await client.get("https://www.arbeitnow.com/api/job-board-api", headers=UA)
    r.raise_for_status()
    out = []
    for j in r.json().get("data", []):
        out.append(_mk(
            "Arbeitnow", j.get("title"), j.get("company_name"),
            j.get("location"), j.get("url"),
            j.get("description"), None, remote=j.get("remote"),
        ))
    return out


async def fetch_jobicy(client) -> list[dict]:
    r = await client.get("https://jobicy.com/api/v2/remote-jobs?count=100", headers=UA)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append(_mk(
            "Jobicy", j.get("jobTitle"), j.get("companyName"),
            j.get("jobGeo"), j.get("url"),
            j.get("jobExcerpt"), j.get("pubDate"), remote=True,
        ))
    return out


async def fetch_adzuna(client, roles=None, broad=True) -> list[dict]:
    """Free Adzuna key — the main source of on-site Bengaluru jobs. Pulls a few
    broad pages, PLUS a targeted Bengaluru search for each role users want (so
    niche roles like 'game developer' actually show up). Set broad=False for a
    fast, role-only search (used by the instant 'Search now' button)."""
    if not (config.ADZUNA_APP_ID and config.ADZUNA_APP_KEY):
        return []
    base = f"https://api.adzuna.com/v1/api/jobs/{config.ADZUNA_COUNTRY}/search/"

    async def query(page: int, what: str | None = None) -> list[dict]:
        params = {
            "app_id": config.ADZUNA_APP_ID,
            "app_key": config.ADZUNA_APP_KEY,
            "results_per_page": 50,
            "where": "Bangalore",
            "max_days_old": 30,
            "content-type": "application/json",
        }
        if what:
            params["what"] = what
        r = await client.get(base + str(page), params=params, headers=UA)
        if r.status_code != 200:
            return []
        out = []
        for j in r.json().get("results", []):
            loc = (j.get("location") or {}).get("display_name", "")
            out.append(_mk(
                "Adzuna", j.get("title"), (j.get("company") or {}).get("display_name"),
                loc, j.get("redirect_url"),
                j.get("description"), j.get("created"),
            ))
        return out

    jobs: list[dict] = []
    if broad:
        for page in (1, 2, 3):                   # broad Bengaluru coverage
            jobs += await query(page)
    done = set()
    for role in (roles or []):                   # targeted per requested role
        role = (role or "").strip()
        if role and role.lower() not in done:
            done.add(role.lower())
            jobs += await query(1, what=role)
    return jobs


async def search_adzuna_roles(roles) -> list[dict]:
    """Fast, role-only Adzuna pull for the instant 'Search now' button."""
    roles = [r for r in (roles or []) if r and r.strip()]
    if not roles:
        return []
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        return await fetch_adzuna(client, roles, broad=False)


async def fetch_themuse(client) -> list[dict]:
    """The Muse — one of the few free sources with on-site Bengaluru/India jobs."""
    out = []
    for page in (1, 2, 3):
        r = await client.get(
            "https://www.themuse.com/api/public/jobs",
            params={"page": page, "location": ["Bengaluru, India", "India"]},
            headers=UA,
        )
        if r.status_code != 200:
            break
        for j in r.json().get("results", []):
            loc = ", ".join(l.get("name", "") for l in j.get("locations", []))
            out.append(_mk(
                "TheMuse", j.get("name"), (j.get("company") or {}).get("name"),
                loc, (j.get("refs") or {}).get("landing_page"),
                j.get("contents"), j.get("publication_date"),
            ))
    return out


async def fetch_himalayas(client) -> list[dict]:
    r = await client.get("https://himalayas.app/jobs/api?limit=100", headers=UA)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        locs = j.get("locationRestrictions") or []
        loc = ", ".join(locs) if locs else "Worldwide"
        posted = ""
        ts = j.get("pubDate")
        if isinstance(ts, (int, float)):
            try:
                posted = dt.datetime.fromtimestamp(ts).isoformat()
            except (OverflowError, OSError, ValueError):
                posted = ""
        out.append(_mk(
            "Himalayas", j.get("title"), j.get("companyName"),
            loc, j.get("guid") or j.get("applicationLink"),
            j.get("description") or j.get("excerpt"), posted, remote=True,
        ))
    return out


async def fetch_weworkremotely(client) -> list[dict]:
    r = await client.get("https://weworkremotely.com/remote-jobs.rss", headers=UA)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    out = []
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        company, sep, role = title.partition(":")
        if sep and role.strip():
            company, title = company.strip(), role.strip()
        else:
            company = ""
        region = (it.findtext("region") or "").strip()
        out.append(_mk(
            "WeWorkRemotely", title, company, region,
            (it.findtext("link") or "").strip(),
            it.findtext("description"), it.findtext("pubDate"), remote=True,
        ))
    return out


FETCHERS = [
    fetch_remotive,
    fetch_remoteok,
    fetch_arbeitnow,
    fetch_jobicy,
    fetch_themuse,
    fetch_himalayas,
    fetch_weworkremotely,
    fetch_adzuna,
]


async def fetch_all(roles=None) -> tuple[list[dict], dict]:
    """Run every source. `roles` (the set users care about) is used to target
    Adzuna's Bengaluru search. Returns (all_jobs, per_source_report)."""
    jobs: list[dict] = []
    report: dict = {}
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        for fetcher in FETCHERS:
            name = fetcher.__name__.replace("fetch_", "")
            try:
                got = await (fetcher(client, roles) if fetcher is fetch_adzuna
                             else fetcher(client))
                jobs.extend(got)
                report[name] = {"ok": True, "count": len(got)}
            except Exception as e:  # noqa: BLE001 - never let one source kill the run
                report[name] = {"ok": False, "error": str(e)[:200]}
    return jobs, report


# ===================== Filtering =====================
# Two layers:
#   passes_location() — a GLOBAL rule applied when jobs are stored. Keeps only
#       on-site Bengaluru jobs and remote jobs an India-based person can take.
#   passes_role()     — a PER-USER rule applied at query time. Strict: only
#       jobs whose TITLE matches the role(s) the user saved.

# Words that describe "remote" without naming a region. If a remote job's
# location is nothing BUT these, it's an unscoped/worldwide role -> India can apply.
_REMOTE_FILLER = ["remote", "flexible", "hybrid", "work from home", "wfh",
                  "work", "from", "home", "only", "fully", "100%", "anywhere in the",
                  "position", "job", "jobs", "contract", "full-time", "part-time",
                  "fulltime", "parttime", "/", "-", ",", "(", ")", "."]


def passes_location(job: dict) -> bool:
    loc = (job.get("location") or "").lower().strip()
    if job.get("remote"):
        if not loc:
            return True  # remote with no stated region -> open worldwide
        if any(t in loc for t in config.REMOTE_INDIA_TERMS):
            return True
        # Generic remote with no specific country named -> treat as worldwide.
        residual = loc
        for w in _REMOTE_FILLER:
            residual = residual.replace(w, " ")
        return not residual.strip()
    # On-site: must be in Bengaluru.
    blob = f"{loc} {job.get('title', '').lower()}"
    return any(t in blob for t in config.BENGALURU_TERMS)


# Words people add out of habit that never appear in a job TITLE — ignore them
# so "crm jobs" / "game developer roles" still match the right titles.
_ROLE_STOPWORDS = {"job", "jobs", "role", "roles", "opening", "openings",
                   "vacancy", "vacancies", "position", "positions", "hiring",
                   "in", "for", "the", "a", "an", "and", "of"}


def passes_role(job: dict, roles: list[str]) -> bool:
    """Strict role match: every meaningful word of a role must appear in the job
    TITLE (filler words like "jobs" are ignored). Empty roles -> match all."""
    roles = [r.strip().lower() for r in (roles or []) if r.strip()]
    if not roles:
        return True
    title = (job.get("title") or "").lower()
    for role in roles:
        raw = [t for t in role.replace("/", " ").replace(",", " ").split() if t]
        tokens = [t for t in raw if t not in _ROLE_STOPWORDS] or raw
        if tokens and all(t in title for t in tokens):
            return True
    return False


def filter_for_user(rows: list[dict], prefs: dict,
                    new_only=False, saved_only=False) -> list[dict]:
    roles = prefs.get("roles", [])
    include_remote = prefs.get("include_remote", True)
    last_seen = prefs.get("last_seen")
    out = []
    for j in rows:
        if not include_remote and j.get("remote"):
            continue
        if not passes_role(j, roles):
            continue
        if saved_only and not j.get("saved"):
            continue
        is_new = bool(last_seen) and (j.get("fetched_at") or "") > last_seen \
            if last_seen else True
        j["is_new"] = 1 if is_new else 0
        if new_only and not is_new:
            continue
        out.append(j)
    return out
