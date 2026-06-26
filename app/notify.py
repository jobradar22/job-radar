"""Notifications: email digest, WhatsApp (via free CallMeBot), and a
cross-platform desktop popup. All best-effort — failures are logged, never raised."""
import smtplib
from email.mime.text import MIMEText

import httpx

from . import config


def send_email(to_email: str, new_jobs: list[dict]) -> bool:
    if not (config.SMTP_HOST and config.SMTP_USER and to_email):
        return False
    if not new_jobs:
        return False

    rows = "".join(
        f"""<tr>
              <td style="padding:8px 12px;border-bottom:1px solid #eee">
                <a href="{j['url']}" style="color:#2563eb;font-weight:600;text-decoration:none">{j['title']}</a><br>
                <span style="color:#555">{j['company']}</span>
                <span style="color:#999"> · {j['location'] or 'N/A'} · {j['source']}</span>
              </td>
            </tr>"""
        for j in new_jobs[:50]
    )
    body = f"""
    <div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:640px;margin:auto">
      <h2 style="color:#111">🛰️ JobRadar — {len(new_jobs)} new job(s)</h2>
      <table style="width:100%;border-collapse:collapse">{rows}</table>
      <p style="color:#999;font-size:12px;margin-top:16px">Sent by your local JobRadar.</p>
    </div>"""

    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = f"JobRadar: {len(new_jobs)} new job(s) for you"
    msg["From"] = config.EMAIL_FROM
    msg["To"] = to_email

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
            s.starttls()
            s.login(config.SMTP_USER, config.SMTP_PASS)
            s.sendmail(config.EMAIL_FROM, [to_email], msg.as_string())
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[notify] email failed: {e}")
        return False


def send_whatsapp(phone: str, apikey: str, new_jobs: list[dict]) -> bool:
    """Send a WhatsApp digest via CallMeBot's free API (personal use).
    `phone` must include the country code, e.g. +9198XXXXXXXX."""
    if not (phone and apikey and new_jobs):
        return False
    lines = [f"🛰️ JobRadar: {len(new_jobs)} new job(s) for you"]
    for j in new_jobs[:8]:
        lines.append(f"• {j['title']} — {j['company']}")
    if len(new_jobs) > 8:
        lines.append(f"…and {len(new_jobs) - 8} more. Open the app to see all.")
    text = "\n".join(lines)
    try:
        r = httpx.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": phone, "text": text, "apikey": apikey},
            timeout=25,
        )
        ok = r.status_code == 200
        if not ok:
            print(f"[notify] whatsapp HTTP {r.status_code}: {r.text[:120]}")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"[notify] whatsapp failed: {e}")
        return False


def desktop_notify(new_jobs: list[dict]) -> bool:
    if not new_jobs:
        return False
    try:
        from plyer import notification

        top = new_jobs[0]
        more = f" (+{len(new_jobs) - 1} more)" if len(new_jobs) > 1 else ""
        notification.notify(
            title=f"🛰️ {len(new_jobs)} new job(s)",
            message=f"{top['title']} · {top['company']}{more}",
            app_name="JobRadar",
            timeout=10,
        )
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[notify] desktop notification failed: {e}")
        return False
