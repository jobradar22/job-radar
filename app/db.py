"""Data layer. Works with two backends, chosen by env vars:
  * Turso / libSQL (cloud, persistent)  — when TURSO_URL + TURSO_TOKEN are set
  * local SQLite file                   — otherwise (local dev)
Jobs are a global pool; each user has their own role preference, saved/hidden
state, and "last seen" marker. All queries go through _query/_execute so both
backends behave identically (rows always come back as plain dicts)."""
import datetime as dt
import os
import threading

from . import auth, config

TURSO_URL = os.getenv("TURSO_URL", "")
TURSO_TOKEN = os.getenv("TURSO_TOKEN", "")
USE_TURSO = bool(TURSO_URL and TURSO_TOKEN)

_lock = threading.Lock()
_client = None

if USE_TURSO:
    import libsql_client
    # libsql-client speaks HTTP; normalize the libsql:// scheme to https://
    _http_url = TURSO_URL.replace("libsql://", "https://")
    _client = libsql_client.create_client_sync(url=_http_url, auth_token=TURSO_TOKEN)

# Schema as individual statements (libSQL has no executescript).
_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT,
        remote INTEGER DEFAULT 0, url TEXT, source TEXT, description TEXT,
        posted_at TEXT, fetched_at TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_jobs_fetched ON jobs(fetched_at)",
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, email TEXT, prefs TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS user_jobs (
        user_id INTEGER, job_id TEXT, saved INTEGER DEFAULT 0,
        dismissed INTEGER DEFAULT 0, PRIMARY KEY (user_id, job_id))""",
]


# --------------------------------------------------------- backend I/O ----
def _sqlite_conn():
    import sqlite3
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _query(sql: str, params=()) -> list[dict]:
    """Run a SELECT, return rows as a list of dicts."""
    params = list(params)
    if USE_TURSO:
        with _lock:
            rs = _client.execute(sql, params)
        cols = rs.columns
        return [dict(zip(cols, row)) for row in rs.rows]
    conn = _sqlite_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _execute(sql: str, params=()):
    """Run a single write statement (autocommitted)."""
    params = list(params)
    if USE_TURSO:
        with _lock:
            _client.execute(sql, params)
        return
    conn = _sqlite_conn()
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _executemany(sql: str, rows: list):
    """Bulk write — one batched round trip on Turso, executemany on SQLite."""
    if not rows:
        return
    if USE_TURSO:
        stmts = [libsql_client.Statement(sql, list(r)) for r in rows]
        with _lock:
            _client.batch(stmts)
        return
    conn = _sqlite_conn()
    try:
        conn.executemany(sql, [tuple(r) for r in rows])
        conn.commit()
    finally:
        conn.close()


def init_db():
    for stmt in _SCHEMA:
        _execute(stmt)


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------- users -----
def create_user(username: str, password: str, email: str = "") -> dict | None:
    username = username.strip().lower()
    if not username or not password:
        return None
    if _query("SELECT 1 FROM users WHERE username=?", (username,)):
        return None
    _execute(
        "INSERT INTO users(username, password_hash, email, prefs, created_at) VALUES(?,?,?,?,?)",
        (username, auth.hash_password(password), email.strip(),
         config.to_json(config.DEFAULT_PREFS), _now()),
    )
    return get_user(username)


def get_user(username: str) -> dict | None:
    rows = _query("SELECT * FROM users WHERE username=?", (username.strip().lower(),))
    return _user_row(rows[0]) if rows else None


def get_user_by_id(user_id: int) -> dict | None:
    rows = _query("SELECT * FROM users WHERE id=?", (user_id,))
    return _user_row(rows[0]) if rows else None


def _user_row(row: dict) -> dict | None:
    if not row:
        return None
    prefs = dict(config.DEFAULT_PREFS)
    prefs.update(config.from_json(row.get("prefs") or "{}"))
    return {"id": row["id"], "username": row["username"], "email": row.get("email") or "",
            "password_hash": row["password_hash"], "prefs": prefs}


def verify_user(username: str, password: str) -> dict | None:
    u = get_user(username)
    if u and auth.verify_password(password, u["password_hash"]):
        return u
    return None


def all_users() -> list[dict]:
    return [_user_row(r) for r in _query("SELECT * FROM users")]


def update_prefs(user_id: int, new_prefs: dict) -> dict:
    u = get_user_by_id(user_id)
    prefs = u["prefs"]
    prefs.update(new_prefs)
    _execute("UPDATE users SET prefs=? WHERE id=?", (config.to_json(prefs), user_id))
    return prefs


def update_email(user_id: int, email: str):
    _execute("UPDATE users SET email=? WHERE id=?", (email.strip(), user_id))


def mark_seen(user_id: int):
    update_prefs(user_id, {"last_seen": _now()})


def set_user_job_flag(user_id: int, job_id: str, field: str, value: int):
    if field not in ("saved", "dismissed"):
        raise ValueError("invalid field")
    _execute(
        "INSERT INTO user_jobs(user_id, job_id) VALUES(?,?) "
        "ON CONFLICT(user_id, job_id) DO NOTHING",
        (user_id, job_id),
    )
    _execute(f"UPDATE user_jobs SET {field}=? WHERE user_id=? AND job_id=?",
             (value, user_id, job_id))


# -------------------------------------------------------------- jobs -----
_INSERT_JOB = """INSERT INTO jobs
    (id,title,company,location,remote,url,source,description,posted_at,fetched_at)
    VALUES (?,?,?,?,?,?,?,?,?,?)"""


def upsert_jobs(jobs: list[dict], now_iso: str) -> list[dict]:
    """Insert jobs we've never seen (already location-filtered). Returns new ones."""
    existing = {r["id"] for r in _query("SELECT id FROM jobs")}
    seen, fresh = set(existing), []
    for j in jobs:
        if j["id"] in seen:
            continue
        seen.add(j["id"])
        fresh.append(j)
    rows = [
        (j["id"], j["title"], j["company"], j["location"],
         1 if j["remote"] else 0, j["url"], j["source"],
         j["description"], j["posted_at"], now_iso)
        for j in fresh
    ]
    _executemany(_INSERT_JOB, rows)
    return fresh


def _candidate_rows(user_id: int, query="", source="") -> list[dict]:
    sql = """SELECT j.*, COALESCE(uj.saved,0) saved, COALESCE(uj.dismissed,0) dismissed
             FROM jobs j
             LEFT JOIN user_jobs uj ON uj.job_id=j.id AND uj.user_id=?
             WHERE COALESCE(uj.dismissed,0)=0"""
    params: list = [user_id]
    if query:
        sql += " AND (LOWER(j.title) LIKE ? OR LOWER(j.company) LIKE ?)"
        like = f"%{query.lower()}%"
        params += [like, like]
    if source:
        sql += " AND j.source=?"
        params.append(source)
    sql += " ORDER BY j.fetched_at DESC, j.posted_at DESC LIMIT 2000"
    return _query(sql, params)
