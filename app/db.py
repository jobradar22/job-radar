"""SQLite layer. Jobs are a global pool (fetched once for everyone); each user
has their own role preference, saved/hidden state, and "last seen" marker."""
import datetime as dt
from contextlib import contextmanager

from . import auth, config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,   -- stable hash of source+url
    title       TEXT,
    company     TEXT,
    location    TEXT,
    remote      INTEGER DEFAULT 0,
    url         TEXT,
    source      TEXT,
    description TEXT,
    posted_at   TEXT,
    fetched_at  TEXT                 -- when we first saw it
);
CREATE INDEX IF NOT EXISTS idx_jobs_fetched ON jobs(fetched_at);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email         TEXT,
    prefs         TEXT,              -- JSON (roles, include_remote, ...)
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS user_jobs (
    user_id   INTEGER,
    job_id    TEXT,
    saved     INTEGER DEFAULT 0,
    dismissed INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, job_id)
);
"""


@contextmanager
def get_conn():
    import sqlite3
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(_SCHEMA)


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------- users -----
def create_user(username: str, password: str, email: str = "") -> dict | None:
    username = username.strip().lower()
    if not username or not password:
        return None
    with get_conn() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            return None
        conn.execute(
            "INSERT INTO users(username, password_hash, email, prefs, created_at) VALUES(?,?,?,?,?)",
            (username, auth.hash_password(password), email.strip(),
             config.to_json(config.DEFAULT_PREFS), _now()),
        )
    return get_user(username)


def get_user(username: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
    return _user_row(row)


def get_user_by_id(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _user_row(row)


def _user_row(row) -> dict | None:
    if not row:
        return None
    prefs = dict(config.DEFAULT_PREFS)
    prefs.update(config.from_json(row["prefs"] or "{}"))
    return {"id": row["id"], "username": row["username"], "email": row["email"] or "",
            "password_hash": row["password_hash"], "prefs": prefs}


def verify_user(username: str, password: str) -> dict | None:
    u = get_user(username)
    if u and auth.verify_password(password, u["password_hash"]):
        return u
    return None


def all_users() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT id FROM users").fetchall()
    return [get_user_by_id(r["id"]) for r in rows]


def update_prefs(user_id: int, new_prefs: dict) -> dict:
    u = get_user_by_id(user_id)
    prefs = u["prefs"]
    prefs.update(new_prefs)
    with get_conn() as conn:
        conn.execute("UPDATE users SET prefs=? WHERE id=?", (config.to_json(prefs), user_id))
    return prefs


def update_email(user_id: int, email: str):
    with get_conn() as conn:
        conn.execute("UPDATE users SET email=? WHERE id=?", (email.strip(), user_id))


def mark_seen(user_id: int):
    update_prefs(user_id, {"last_seen": _now()})


def set_user_job_flag(user_id: int, job_id: str, field: str, value: int):
    if field not in ("saved", "dismissed"):
        raise ValueError("invalid field")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO user_jobs(user_id, job_id) VALUES(?,?) "
            "ON CONFLICT(user_id, job_id) DO NOTHING",
            (user_id, job_id),
        )
        conn.execute(f"UPDATE user_jobs SET {field}=? WHERE user_id=? AND job_id=?",
                     (value, user_id, job_id))


# -------------------------------------------------------------- jobs -----
def upsert_jobs(jobs: list[dict], now_iso: str) -> list[dict]:
    """Insert jobs we've never seen (already location-filtered). Returns new ones."""
    new_jobs = []
    with get_conn() as conn:
        for j in jobs:
            if conn.execute("SELECT 1 FROM jobs WHERE id=?", (j["id"],)).fetchone():
                continue
            conn.execute(
                """INSERT INTO jobs
                   (id,title,company,location,remote,url,source,description,posted_at,fetched_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (j["id"], j["title"], j["company"], j["location"],
                 1 if j["remote"] else 0, j["url"], j["source"],
                 j["description"], j["posted_at"], now_iso),
            )
            new_jobs.append(j)
    return new_jobs


def _candidate_rows(user_id: int, query="", source=""):
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
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
