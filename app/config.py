"""Configuration. Infra/secrets come from environment (.env); per-user
preferences (which role to search) live in the database, set after login."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_PATH = os.getenv("JOBRADAR_DB", str(BASE_DIR / "jobradar.db"))

# How often the background scheduler re-checks all sources (minutes).
REFRESH_MINUTES = int(os.getenv("REFRESH_MINUTES", "30"))

# Network
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# --- Auth ---
# Signs the login cookie. Set a long random value in production.
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-please-set-SECRET_KEY")
# Optional: require a code to create an account (stops random public signups).
# Leave blank to allow open registration.
REGISTRATION_CODE = os.getenv("REGISTRATION_CODE", "")

# --- Email (optional). Used to SEND alerts; each user receives at their own
#     address saved in their profile. Leave blank to disable email. ---
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", os.getenv("SMTP_USER", ""))

# --- Adzuna (optional, free key) — main source of on-site Bengaluru jobs. ---
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
ADZUNA_COUNTRY = os.getenv("ADZUNA_COUNTRY", "in")  # 'in' = India

# =================== Location rules (apply to all users) ===================
# On-site jobs are kept ONLY if they are in Bengaluru.
BENGALURU_TERMS = ["bengaluru", "bangalore", "bengalore"]
# A REMOTE job is kept only if an India-based candidate can take it: it must
# either mention India/Bengaluru, or be open to a region that includes India
# (worldwide / anywhere / global / asia / apac), or name no specific region.
REMOTE_INDIA_TERMS = [
    "india", "bengaluru", "bangalore",
    "anywhere", "worldwide", "world wide", "global",
    "asia", "apac", "asia pacific",
]

# Default preferences for a new account (editable after login).
DEFAULT_PREFS = {
    "roles": [],          # e.g. ["python developer"]. Empty = show all roles.
    "include_remote": True,
    "notify_email": True,
    "notify_whatsapp": False,
    "whatsapp_phone": "",   # with country code, e.g. +9198XXXXXXXX
    "whatsapp_apikey": "",  # the key CallMeBot gives you (see README)
    "last_seen": None,    # ISO timestamp; jobs newer than this show a NEW badge
}


def to_json(d) -> str:
    return json.dumps(d)


def from_json(s: str):
    try:
        return json.loads(s)
    except (TypeError, json.JSONDecodeError):
        return {}
